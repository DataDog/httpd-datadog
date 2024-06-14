#include "hooks.h"

#include <datadog/injection_options.h>
#include <datadog/span.h>
#include <datadog/span_config.h>
#include <datadog/string_view.h>
#include <datadog/tracer.h>
#include <fmt/core.h>

#include "../utils.h"
#include "common_conf.h"
#include "utils.h"

namespace datadog::tracing {
namespace {

std::string protocol(int protocol_number) {
  switch (protocol_number) {
    case 9:
      return "0.9";
    case 1000:
      return "1.0";
    case 1001:
      return "1.1";
    case 2000:
      return "2.0";
    case 3000:
      return "3.0";
    default:
      return "";
  }
}

static SpanConfig make_span_config(
    request_rec* r, std::unordered_map<std::string, std::string> default_tags) {
  static const std::string httpd_version = common::utils::make_httpd_version();
  std::string resource_name{r->method};
  resource_name += " ";
  resource_name += r->uri;
  resource_name += " ";
  resource_name += r->protocol;

  datadog::tracing::SpanConfig options;
  options.name =
      (r->proxyreq != PROXYREQ_NONE) ? "httpd.proxy" : "httpd.request";
  options.resource = resource_name;
  options.tags = std::unordered_map<std::string, std::string>{
      {"component", "httpd"},
      {"httpd.version", httpd_version},
      {"httpd.virtual_host", r->server->is_virtual ? "true" : "false"},
      {"httpd.mpm", ap_show_mpm()},
      {"http.version", protocol(r->proto_num)},
      {"http.host", r->hostname},
      {"http.method", r->method},
      {"http.url", r->unparsed_uri},
      {"http.request.content_length", std::to_string(r->clength)},
  };
  options.tags.merge(default_tags);

  if (r->useragent_ip) options.tags.emplace("http.client_ip", r->useragent_ip);

  if (auto user_agent = apr_table_get(r->headers_in, "User-Agent")) {
    options.tags.emplace("http.useragent", user_agent);
  }

  return options;
}

apr_status_t delete_span(void* data) {
  auto* span = static_cast<datadog::tracing::Span*>(data);
  delete span;

  return 0;
}

}  // namespace

int on_fixups(request_rec* r, Tracer& g_tracer, module* datadog_module) {
  Span* span = nullptr;
  InjectionOptions injection_opts;

  if (r->prev || r->main != nullptr) {
    // Trace internal redirection or subrequests
    // TODO: What if `per_dir_config` is not copied for each
    //       subrequests/internal redirection?
    request_rec* main_r = r->prev ? r->prev : r->main;

    auto* dir_conf = static_cast<conf::Directory*>(
        ap_get_module_config(main_r->per_dir_config, datadog_module));
    if (dir_conf == nullptr || !dir_conf->tracing_enabled) return DECLINED;

    void* data = ap_get_module_config(main_r->request_config, datadog_module);
    if (!data) return DECLINED;

    Span* parent_span = static_cast<Span*>(data);
    SpanConfig options = make_span_config(r, dir_conf->tags);
    options.name = "httpd.subrequests";
    span = new Span(parent_span->create_child(options));
    injection_opts.delegate_sampling_decision = dir_conf->delegate_sampling;
  } else {
    // Trace request
    auto* dir_conf = static_cast<datadog::conf::Directory*>(
        ap_get_module_config(r->per_dir_config, datadog_module));
    if (dir_conf == nullptr || !dir_conf->tracing_enabled) return DECLINED;

    void* data = ap_get_module_config(r->request_config, datadog_module);
    if (data)
      return DECLINED;  ///< `start_span` can not be called twice on the same
                        ///< request

    SpanConfig options = make_span_config(r, dir_conf->tags);

    // In case we fail to use the inbound span, then, start a new trace
    // ¯\_(ツ)_/¯ There is nothing we can do about it.
    if (dir_conf->trust_inbound_span) {
      auto extracted_span = g_tracer.extract_or_create_span(
          utils::HeaderReader(r->headers_in), options);
      if (auto error = extracted_span.if_error()) {
        span = new Span(g_tracer.create_span(options));
        span->set_error(error->message.c_str());
      } else {
        span = new Span(std::move(*extracted_span));
      }
    } else {
      span = new Span(g_tracer.create_span(options));
    }

    injection_opts.delegate_sampling_decision = dir_conf->delegate_sampling;
  }

  assert(span != nullptr);

  // Register to the request pool to have the same lifecycle as
  // the request.
  ap_set_module_config(r->request_config, datadog_module, (void*)span);
  apr_pool_cleanup_register(r->pool, (void*)span, delete_span,
                            apr_pool_cleanup_null);

  // Add environment variables for log injection
  apr_table_set(r->subprocess_env, "Datadog-Trace-ID",
                span->trace_id().hex_padded().c_str());
  apr_table_set(r->subprocess_env, "Datadog-Span-ID",
                std::to_string(span->id()).c_str());

  utils::HeaderWriter header_injector(r->headers_in);
  span->inject(header_injector, injection_opts);

  return DECLINED;
}

int on_log_transaction(request_rec* r, module* datadog_module) {
  if (r->main) return DECLINED;

  void* data = ap_get_module_config(r->request_config, datadog_module);
  if (data == nullptr) return DECLINED;

  auto* span = static_cast<Span*>(data);
  if (!span) return DECLINED;

  span->set_tag("http.status_code", std::to_string(r->status));
  span->set_tag("http.response.content_length", std::to_string(r->bytes_sent));

  if (r->status >= 500) {
    span->set_error(true);

    if (const char* error_msg = apr_table_get(r->notes, "error-notes");
        error_msg != nullptr) {
      span->set_error_message(error_msg);
    }
  }

  utils::HeaderReader reader(r->headers_out);
  span->read_sampling_delegation_response(reader);

  return DECLINED;
}

}  // namespace datadog::tracing
