#include "rum/filter.h"

#include <string_view>

#include "common_conf.h"
#include "http_log.h"
#include "telemetry.h"
#include "util_filter.h"
#include "utils.h"

APLOG_USE_MODULE(datadog);

using namespace datadog::conf;
using namespace datadog::rum;
using namespace std::literals;

constexpr std::string_view k_injected_header = "x-datadog-sdk-injected";

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
                "RUM injector is correctly initialized.");
}

bool should_inject(rum_filter_ctx& ctx, request_rec& r) {
  if (ctx.state != InjectionState::pending) {
    return false;
  }

  const char* const already_injected =
      apr_table_get(r.headers_out, k_injected_header.data());
  if (already_injected && std::string_view(already_injected) == "1") {
    telemetry::injection_skip::already_injected->inc();
    ctx.state = InjectionState::done;
    return false;
  }

  const char* const content_type = apr_table_get(r.headers_out, "Content-Type");
  if (content_type && datadog::common::utils::contains(
                          std::string_view(content_type), "text/html"sv)) {
    telemetry::injection_skip::invalid_content_type->inc();
    return false;
  }

  const char* const content_encoding =
      apr_table_get(r.headers_out, "Content-Encoding");
  if (content_encoding) {
    telemetry::injection_skip::compressed_html->inc();
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

  if (!dir_conf->rum.enabled || dir_conf->rum.snippet == nullptr) {
    return ap_pass_brigade(f->next, bb);
  }

  // First time the filter is being called -> Init the context
  if (f->ctx == nullptr) {
    init_rum_context(f, dir_conf->rum.snippet);
    const char* const csp_header =
        apr_table_get(r->headers_out, "Content-Security-Policy");
    if (csp_header && !std::string_view(csp_header).empty()) {
      telemetry::content_security_policy->inc();
    }
  }

  auto* ctx = static_cast<rum_filter_ctx*>(f->ctx);

  if (!should_inject(*ctx, *r)) {
    return ap_pass_brigade(f->next, bb);
  }

  size_t bytes;
  const char* buffer;

  for (apr_bucket* b = APR_BRIGADE_FIRST(bb); b != APR_BRIGADE_SENTINEL(bb);
       b = APR_BUCKET_NEXT(b)) {
    if (APR_BUCKET_IS_EOS(b)) {
      injector_end(ctx->injector);
      telemetry::injection_failed->inc();
    } else if (APR_BUCKET_IS_METADATA(b)) {
      // TODO: Handle metadata bucket like flush
    } else if (apr_bucket_read(b, &buffer, &bytes, APR_BLOCK_READ) ==
               APR_SUCCESS) {
      InjectorResult result =
          injector_write(ctx->injector, (const uint8_t*)buffer, bytes);

      size_t offset = 0;
      for (size_t i = 0; i < result.slices_length; i++) {
        const BytesSlice* slice = result.slices + i;
        if (slice->from_incoming_chunk) {
          offset += slice->length;
        } else {
          apr_bucket* b_snippet = apr_bucket_immortal_create(
              (const char*)slice->start, slice->length,
              f->r->connection->bucket_alloc);

          apr_bucket_split(b, offset);
          APR_BUCKET_INSERT_AFTER(b, b_snippet);
          offset += slice->length;
        }
      }
      if (result.injected) {
        ctx->state = InjectionState::done;
        apr_table_set(r->headers_out, k_injected_header.data(), "1");

        telemetry::injection_succeed->inc();
        return ap_pass_brigade(f->next, bb);
      }
    }
  }

  return ap_pass_brigade(f->next, bb);
}
