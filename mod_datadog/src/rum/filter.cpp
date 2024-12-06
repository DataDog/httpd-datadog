#include "rum/filter.h"

#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <string_view>

#include "common_conf.h"
#include "http_log.h"
#include "util_filter.h"
#include "utils.h"

APLOG_USE_MODULE(datadog);

using namespace datadog::conf;
using namespace std::literals;

constexpr std::string_view k_injected_header = "x-datadog-sdk-injected";

namespace {
std::string make_rum_json_config(
    std::string_view config_version,
    const std::unordered_map<std::string, std::string>& config) {
  rapidjson::Document doc;
  doc.SetObject();

  rapidjson::Document::AllocatorType& allocator = doc.GetAllocator();
  doc.AddMember("majorVersion",
                rapidjson::Value(std::stoi(config_version.data() + 1)),
                allocator);

  rapidjson::Value rum(rapidjson::kObjectType);
  for (const auto& [key, value] : config) {
    if (key == "majorVersion") {
      continue;
    } else if (key == "sessionSampleRate" || key == "sessionReplaySampleRate") {
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(std::stod(value)).Move(), allocator);
    } else if (key == "trackResources" || key == "trackLongTasks" ||
               key == "trackUserInteractions") {
      auto b = (value == "true" ? true : false);
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(b).Move(), allocator);
    } else {
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(value.c_str(), allocator).Move(),
                    allocator);
    }
  }

  doc.AddMember("rum", rum, allocator);

  // Convert the document to a JSON string
  rapidjson::StringBuffer buffer;
  rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
  doc.Accept(writer);

  return buffer.GetString();
}
}  // namespace

static void init_rum_context(
    ap_filter_t* f,
    const std::unordered_map<std::string, std::string>& rum_config) {
  request_rec* r = f->r;
  f->ctx = apr_pcalloc(r->pool, sizeof(rum_filter_ctx));
  auto* ctx = (rum_filter_ctx*)f->ctx;

  const auto json_config = make_rum_json_config("v5", rum_config);
  if (json_config.empty()) {
    ap_log_rerror(APLOG_MARK, APLOG_ERR, 0, r,
                  "failed to generate the RUM SDK script");
    ctx->state = InjectionState::error;
    return;
  }

  Snippet* snippet = snippet_create_from_json(json_config.c_str());
  if (snippet->error_code != 0) {
    ap_log_rerror(APLOG_MARK, APLOG_ERR, 0, r,
                  "failed to initial RUM SDK injector: %s",
                  snippet->error_message);
    ctx->state = InjectionState::error;
    return;
  }

  ctx->state = InjectionState::pending;

  ctx->snippet = snippet;
  apr_pool_cleanup_register(
      r->pool, (void*)ctx->snippet,
      [](void* p) -> apr_status_t {
        snippet_cleanup((Snippet*)p);
        return 0;
      },
      apr_pool_cleanup_null);

  ctx->injector = injector_create(ctx->snippet);
  apr_pool_cleanup_register(
      r->pool, (void*)ctx->injector,
      [](void* p) -> apr_status_t {
        injector_cleanup((Injector*)p);
        return 0;
      },
      apr_pool_cleanup_null);
  ap_log_rerror(APLOG_MARK, APLOG_INFO, 0, r,
                "RUM module is correctly initialized.");
}

bool should_inject(rum_filter_ctx& ctx, request_rec& r) {
  if (ctx.state != InjectionState::pending) {
    return false;
  }

  const char* const already_injected =
      apr_table_get(r.headers_out, k_injected_header.data());
  if (already_injected && std::string_view(already_injected) == "1") {
    ctx.state = InjectionState::done;
    return false;
  }

  const char* const content_type = apr_table_get(r.headers_out, "Content-Type");
  if (content_type && datadog::common::utils::contains(
                          std::string_view(content_type), "text/html"sv)) {
    return false;
  }

  const char* const content_encoding =
      apr_table_get(r.headers_out, "Content-Encoding");
  if (content_encoding) {
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
  request_rec* r = f->r;

  auto* dir_conf = static_cast<Directory*>(
      ap_get_module_config(r->per_dir_config, &datadog_module));

  if (!dir_conf->rum_enabled) {
    return ap_pass_brigade(f->next, bb);
  }

  if (dir_conf->rum_config.empty()) {
    ap_log_rerror(
        APLOG_MARK, APLOG_WARNING, 0, r,
        "RUM SDK Injection is enabled but no JSON configuration found");
    return ap_pass_brigade(f->next, bb);
  }

  // First time the filter is being called -> Init the context
  if (f->ctx == nullptr) {
    init_rum_context(f, dir_conf->rum_config);
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

        return ap_pass_brigade(f->next, bb);
      }
    }
  }

  return ap_pass_brigade(f->next, bb);
}
