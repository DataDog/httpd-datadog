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
                            const datadog::rum::conf::Directory& rum_conf);
static void count_csp_header(const request_rec& request);
static void inject_into_brigade(rum_filter_ctx& ctx, request_rec& request,
                                const datadog::rum::conf::Directory& rum_conf,
                                apr_bucket_brigade& brigade);
static bool inject_into_bucket(rum_filter_ctx& ctx, request_rec& request,
                               apr_bucket* bucket);
static void record_injection(rum_filter_ctx& ctx, request_rec& request,
                             const datadog::rum::conf::Directory& rum_conf);
static void insert_injection_slices(apr_bucket* bucket,
                                    const InjectorResult& result,
                                    apr_bucket_alloc_t* allocator);

static void init_rum_context(ap_filter_t* filter, Snippet* snippet) {
  request_rec* const request = filter->r;
  filter->ctx = apr_pcalloc(request->pool, sizeof(rum_filter_ctx));
  rum_filter_ctx* const ctx = static_cast<rum_filter_ctx*>(filter->ctx);

  ctx->state = InjectionState::pending;

  ctx->injector = injector_create(snippet);
  apr_pool_cleanup_register(
      request->pool, ctx->injector,
      [](void* injector) -> apr_status_t {
        injector_cleanup(static_cast<Injector*>(injector));
        return 0;
      },
      apr_pool_cleanup_null);
  ap_log_rerror(APLOG_MARK, APLOG_INFO, 0, request,
                "[RUM] injector is correctly initialized.");
}

bool should_inject(rum_filter_ctx& ctx, request_rec& request,
                   const datadog::rum::conf::Directory& rum_conf) {
  if (ctx.state != InjectionState::pending) {
    return false;
  }

  const char* const already_injected =
      apr_table_get(request.headers_out, k_injected_header.data());
  if (already_injected && std::string_view(already_injected) == "1") {
    count_injection(telemetry::injection_skipped, "reason:already_injected",
                    rum_conf);
    ctx.state = InjectionState::done;
    return false;
  }

  // Apache sets the outgoing header after resource filters. Read its media
  // type from the request record.
  const char* const content_type = request.content_type;
  if (!is_html_content_type(content_type)) {
    ap_log_rerror(
        APLOG_MARK, APLOG_DEBUG, 0, &request,
        "[RUM] Skip injection: \"Content-Type: %s\" does not match text/html.",
        content_type ? content_type : "<unset>");
    count_injection(telemetry::injection_skipped, "reason:content-type",
                    rum_conf);
    ctx.state = InjectionState::done;
    return false;
  }

  const char* const content_encoding =
      apr_table_get(request.headers_out, "Content-Encoding");
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
int rum_output_filter(ap_filter_t* filter, apr_bucket_brigade* brigade) {
  assert(brigade != nullptr);

  request_rec* const request = filter->r;
  Directory* const dir_conf = static_cast<Directory*>(
      ap_get_module_config(request->per_dir_config, &datadog_module));
  const datadog::rum::conf::Directory& rum_conf = dir_conf->rum;

  if (rum_conf.enabled != true || rum_conf.snippet == nullptr) {
    return ap_pass_brigade(filter->next, brigade);
  }

  if (filter->ctx == nullptr) {
    init_rum_context(filter, rum_conf.snippet);
    count_csp_header(*request);
  }

  rum_filter_ctx* const ctx = static_cast<rum_filter_ctx*>(filter->ctx);
  if (!should_inject(*ctx, *request, rum_conf)) {
    return ap_pass_brigade(filter->next, brigade);
  }

  // Injection changes the body size. Clear the length before headers are sent.
  apr_table_unset(request->headers_out, "Content-Length");
  request->clength = -1;

  inject_into_brigade(*ctx, *request, rum_conf, *brigade);
  return ap_pass_brigade(filter->next, brigade);
}

static void count_csp_header(const request_rec& request) {
  const char* const csp_header =
      apr_table_get(request.headers_out, "Content-Security-Policy");
  if (csp_header && !std::string_view(csp_header).empty()) {
    datadog::telemetry::counter::increment(
        telemetry::content_security_policy,
        telemetry::build_tags("status:seen", "kind:header"));
  }
}

static void inject_into_brigade(rum_filter_ctx& ctx, request_rec& request,
                                const datadog::rum::conf::Directory& rum_conf,
                                apr_bucket_brigade& brigade) {
  for (apr_bucket* bucket = APR_BRIGADE_FIRST(&brigade);
       bucket != APR_BRIGADE_SENTINEL(&brigade);
       bucket = APR_BUCKET_NEXT(bucket)) {
    if (APR_BUCKET_IS_EOS(bucket)) {
      injector_end(ctx.injector);
      count_injection(telemetry::injection_failed, "reason:missing_header_tag",
                      rum_conf);
    } else if (APR_BUCKET_IS_METADATA(bucket)) {
      // TODO: Handle metadata bucket like flush
    } else if (inject_into_bucket(ctx, request, bucket)) {
      record_injection(ctx, request, rum_conf);
      return;
    }
  }

  ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, &request,
                "[RUM] failed to inject the browser SDK.");
}

static bool inject_into_bucket(rum_filter_ctx& ctx, request_rec& request,
                               apr_bucket* bucket) {
  const char* data;
  apr_size_t length;
  if (apr_bucket_read(bucket, &data, &length, APR_BLOCK_READ) != APR_SUCCESS) {
    return false;
  }

  const InjectorResult result = injector_write(
      ctx.injector, reinterpret_cast<const uint8_t*>(data), length);
  insert_injection_slices(bucket, result, request.connection->bucket_alloc);
  return result.injected;
}

static void record_injection(rum_filter_ctx& ctx, request_rec& request,
                             const datadog::rum::conf::Directory& rum_conf) {
  ctx.state = InjectionState::done;
  apr_table_set(request.headers_out, k_injected_header.data(), "1");
  ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, &request,
                "[RUM] successfully injected the browser SDK.");
  datadog::telemetry::counter::increment(
      telemetry::injection_succeed,
      telemetry::build_tags(rum_conf.app_id_tag, rum_conf.remote_config_tag));
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

static void count_injection(const datadog::telemetry::Counter& counter,
                            const char* reason,
                            const datadog::rum::conf::Directory& rum_conf) {
  datadog::telemetry::counter::increment(
      counter, telemetry::build_tags(reason, rum_conf.app_id_tag,
                                     rum_conf.remote_config_tag));
}
