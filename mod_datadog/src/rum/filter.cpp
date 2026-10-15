#include "rum/filter.h"

#include <datadog/telemetry/telemetry.h>

#include <string_view>

#include "common_conf.h"
#include "http_log.h"
#include "rum/content_type.h"
#include "telemetry.h"
#include "util_filter.h"

APLOG_USE_MODULE(datadog);

using namespace datadog::conf;
using namespace datadog::rum;

constexpr std::string_view k_injected_header = "x-datadog-sdk-injected";

static void count_injection(const datadog::telemetry::Counter& counter,
                            const char* reason,
                            const datadog::rum::conf::ResolvedConfig& rum_conf);
static void insert_injection_slices(apr_bucket* bucket,
                                    const InjectorResult& result,
                                    apr_bucket_alloc_t* allocator);

static void init_rum_context(ap_filter_t* f, Snippet* snippet) {
  request_rec* r = f->r;
  f->ctx = apr_pcalloc(r->pool, sizeof(rum_filter_ctx));
  auto* ctx = (rum_filter_ctx*)f->ctx;

  ctx->state = InjectionState::pending;

  ctx->injector = injector_create(snippet);
  apr_pool_cleanup_register(
      r->pool, (void*)ctx->injector,
      [](void* p) -> apr_status_t {
        injector_cleanup((Injector*)p);
        return 0;
      },
      apr_pool_cleanup_null);
  ap_log_rerror(APLOG_MARK, APLOG_INFO, 0, r,
                "[RUM] injector is correctly initialized.");
}

bool should_inject(rum_filter_ctx& ctx, request_rec& r,
                   const datadog::rum::conf::ResolvedConfig& rum_conf) {
  if (ctx.state != InjectionState::pending) {
    return false;
  }

  const char* const already_injected =
      apr_table_get(r.headers_out, k_injected_header.data());
  if (already_injected && std::string_view(already_injected) == "1") {
    count_injection(telemetry::injection_skipped, "reason:already_injected",
                    rum_conf);
    ctx.state = InjectionState::done;
    return false;
  }

  // Apache sets the outgoing header after resource filters. Read its media
  // type from the request record.
  const char* const content_type = r.content_type;
  if (!is_html_content_type(content_type)) {
    ap_log_rerror(
        APLOG_MARK, APLOG_DEBUG, 0, &r,
        "[RUM] Skip injection: \"Content-Type: %s\" does not match text/html.",
        content_type ? content_type : "<unset>");
    count_injection(telemetry::injection_skipped, "reason:content-type",
                    rum_conf);
    ctx.state = InjectionState::done;
    return false;
  }

  const char* const content_encoding =
      apr_table_get(r.headers_out, "Content-Encoding");
  if (content_encoding) {
    count_injection(telemetry::injection_skipped, "reason:compressed_html",
                    rum_conf);
    return false;
  }

  return true;
}

/* TODO:
 *   - use AddOutputFilterByType. In theory the scanner can be run on
 *     everything.
 *   - add span for visualing the injection?
 *   - create snippet when the directive is created.
 */
int rum_output_filter(ap_filter_t* f, apr_bucket_brigade* bb) {
  assert(bb != nullptr);

  request_rec* r = f->r;

  auto* dir_conf = static_cast<Directory*>(
      ap_get_module_config(r->per_dir_config, &datadog_module));

  const auto rum_conf =
      datadog::rum::conf::resolve_configuration(dir_conf->rum);

  if (!rum_conf.enabled || rum_conf.snippet == nullptr) {
    // Nothing about this decision can change mid-request, and the filter is
    // inserted unconditionally, so drop out of the chain instead of being
    // re-entered for every brigade of a response we will never touch.
    ap_remove_output_filter(f);
    return ap_pass_brigade(f->next, bb);
  }

  // First time the filter is being called -> Init the context
  if (f->ctx == nullptr) {
    init_rum_context(f, rum_conf.snippet);
    const char* const csp_header =
        apr_table_get(r->headers_out, "Content-Security-Policy");
    if (csp_header && !std::string_view(csp_header).empty()) {
      datadog::telemetry::counter::increment(
          telemetry::content_security_policy,
          telemetry::build_tags("status:seen", "kind:header"));
    }
  }

  auto* ctx = static_cast<rum_filter_ctx*>(f->ctx);

  if (!should_inject(*ctx, *r, rum_conf)) {
    return ap_pass_brigade(f->next, bb);
  }

  // Injection changes the body size. Clear the length before headers are sent.
  apr_table_unset(r->headers_out, "Content-Length");
  r->clength = -1;

  size_t bytes;
  const char* buffer;

  for (apr_bucket* b = APR_BRIGADE_FIRST(bb); b != APR_BRIGADE_SENTINEL(bb);
       b = APR_BUCKET_NEXT(b)) {
    if (APR_BUCKET_IS_EOS(b)) {
      injector_end(ctx->injector);
      count_injection(telemetry::injection_failed, "reason:missing_header_tag",
                      rum_conf);
    } else if (APR_BUCKET_IS_METADATA(b)) {
      // TODO: Handle metadata bucket like flush
    } else if (apr_bucket_read(b, &buffer, &bytes, APR_BLOCK_READ) ==
               APR_SUCCESS) {
      InjectorResult result =
          injector_write(ctx->injector, (const uint8_t*)buffer, bytes);

      insert_injection_slices(b, result, r->connection->bucket_alloc);
      if (result.injected) {
        ctx->state = InjectionState::done;
        apr_table_set(r->headers_out, k_injected_header.data(), "1");

        ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, r,
                      "[RUM] successfully injected the browser SDK.");
        datadog::telemetry::counter::increment(
            telemetry::injection_succeed,
            telemetry::build_tags(rum_conf.app_id_tag,
                                  rum_conf.remote_config_tag));

        return ap_pass_brigade(f->next, bb);
      }
    }
  }

  ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, r,
                "[RUM] failed to inject the browser SDK.");
  return ap_pass_brigade(f->next, bb);
}

static void insert_injection_slices(apr_bucket* bucket,
                                    const InjectorResult& result,
                                    apr_bucket_alloc_t* allocator) {
  size_t offset = 0;
  for (size_t index = 0; index < result.slices_length; ++index) {
    const BytesSlice& slice = result.slices[index];
    if (!slice.from_incoming_chunk) {
      apr_bucket* snippet_bucket = apr_bucket_immortal_create(
          reinterpret_cast<const char*>(slice.start), slice.length, allocator);
      apr_bucket_split(bucket, offset);
      APR_BUCKET_INSERT_AFTER(bucket, snippet_bucket);
    }
    offset += slice.length;
  }
}

static void count_injection(
    const datadog::telemetry::Counter& counter, const char* reason,
    const datadog::rum::conf::ResolvedConfig& rum_conf) {
  datadog::telemetry::counter::increment(
      counter, telemetry::build_tags(reason, rum_conf.app_id_tag,
                                     rum_conf.remote_config_tag));
}
