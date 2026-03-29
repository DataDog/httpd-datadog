#include "rum/filter.h"

#include <datadog/telemetry/telemetry.h>

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
                "[RUM] injector is correctly initialized.");
}

bool should_inject(rum_filter_ctx& ctx, request_rec& r,
                   const datadog::rum::conf::Directory& rum_conf) {
  if (ctx.state != InjectionState::pending) {
    return false;
  }

  const char* const already_injected =
      apr_table_get(r.headers_out, k_injected_header.data());
  if (already_injected && std::string_view(already_injected) == "1") {
    datadog::telemetry::counter::increment(
        telemetry::injection_skipped,
        telemetry::build_tags("reason:already_injected", rum_conf.app_id_tag,
                              rum_conf.remote_config_tag));

    ctx.state = InjectionState::done;
    return false;
  }

  const char* const content_type = apr_table_get(r.headers_out, "Content-Type");
  if (content_type && !datadog::common::utils::contains(
                          std::string_view(content_type), "text/html"sv)) {
    ap_log_rerror(
        APLOG_MARK, APLOG_DEBUG, 0, &r,
        "[RUM] Skip injection: \"Content-Type: %s\" does not match text/html.",
        content_type);
    datadog::telemetry::counter::increment(
        telemetry::injection_skipped,
        telemetry::build_tags("reason:content-type", rum_conf.app_id_tag,
                              rum_conf.remote_config_tag));
    return false;
  }

  const char* const content_encoding =
      apr_table_get(r.headers_out, "Content-Encoding");
  if (content_encoding) {
    datadog::telemetry::counter::increment(
        telemetry::injection_skipped,
        telemetry::build_tags("reason:compressed_html", rum_conf.app_id_tag,
                              rum_conf.remote_config_tag));
    return false;
  }

  return true;
}

static void handle_eos_bucket(request_rec* r, ap_filter_t* f,
                              apr_bucket_brigade* bb, rum_filter_ctx* ctx,
                              Directory* dir_conf) {
  InjectorResult result = injector_end(ctx->injector);
  if (result.injected) {
    apr_bucket_brigade* new_bb =
        apr_brigade_create(r->pool, f->r->connection->bucket_alloc);
    size_t total_length = 0;
    for (size_t i = 0; i < result.slices_length; i++) {
      total_length += result.slices[i].length;
    }

    char* combined_buffer = (char*)apr_palloc(r->pool, total_length);
    size_t offset = 0;
    for (size_t i = 0; i < result.slices_length; i++) {
      const BytesSlice* slice = result.slices + i;
      memcpy(combined_buffer + offset, slice->start, slice->length);
      offset += slice->length;
    }

    apr_bucket* content_bucket = apr_bucket_immortal_create(
        combined_buffer, total_length, f->r->connection->bucket_alloc);
    APR_BRIGADE_INSERT_TAIL(new_bb, content_bucket);

    apr_bucket* eos_bucket =
        apr_bucket_eos_create(f->r->connection->bucket_alloc);
    APR_BRIGADE_INSERT_TAIL(new_bb, eos_bucket);

    apr_brigade_cleanup(bb);
    APR_BRIGADE_CONCAT(bb, new_bb);

    apr_table_set(r->headers_out, k_injected_header.data(), "1");

    ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, r,
                  "[RUM] successfully injected the browser SDK at EOS.");
    datadog::telemetry::counter::increment(
        telemetry::injection_succeed,
        telemetry::build_tags(dir_conf->rum.app_id_tag,
                              dir_conf->rum.remote_config_tag));
  } else {
    ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, r,
                  "[RUM] failed to inject the browser SDK.");
    datadog::telemetry::counter::increment(
        telemetry::injection_failed,
        telemetry::build_tags("reason:missing_header_tag",
                              dir_conf->rum.app_id_tag,
                              dir_conf->rum.remote_config_tag));
  }
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

  // Only inject if explicitly enabled
  if (dir_conf->rum.enabled != true || dir_conf->rum.snippet == nullptr) {
    return ap_pass_brigade(f->next, bb);
  }

  // First time the filter is being called -> Init the context
  if (f->ctx == nullptr) {
    init_rum_context(f, dir_conf->rum.snippet);
    const char* const csp_header =
        apr_table_get(r->headers_out, "Content-Security-Policy");
    if (csp_header && !std::string_view(csp_header).empty()) {
      datadog::telemetry::counter::increment(
          telemetry::content_security_policy,
          telemetry::build_tags("status:seen", "kind:header"));
    }
  }

  auto* ctx = static_cast<rum_filter_ctx*>(f->ctx);

  if (!should_inject(*ctx, *r, dir_conf->rum)) {
    return ap_pass_brigade(f->next, bb);
  }

  size_t bytes;
  const char* buffer;

  for (apr_bucket* b = APR_BRIGADE_FIRST(bb); b != APR_BRIGADE_SENTINEL(bb);
       b = APR_BUCKET_NEXT(b)) {
    if (APR_BUCKET_IS_EOS(b)) {
      handle_eos_bucket(r, f, bb, ctx, dir_conf);
      break;
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

        ap_log_rerror(APLOG_MARK, APLOG_DEBUG, 0, r,
                      "[RUM] successfully injected the browser SDK.");
        datadog::telemetry::counter::increment(
            telemetry::injection_succeed,
            telemetry::build_tags(dir_conf->rum.app_id_tag,
                                  dir_conf->rum.remote_config_tag));

        return ap_pass_brigade(f->next, bb);
      }
    }
  }

  return ap_pass_brigade(f->next, bb);
}
