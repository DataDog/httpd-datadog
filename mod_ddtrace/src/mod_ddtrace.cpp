#include "ap_config.h"
#include "ap_provider.h"
#include "apr_errno.h"
#include "apr_hash.h"
#include "apr_pools.h"
#include "http_core.h"
#include "http_log.h"
#include "http_protocol.h"
#include "http_request.h"
#include "httpd.h"

#include "config.h"
#include "logger.h"

#include <datadog/dict_reader.h>
#include <datadog/dict_writer.h>
#include <datadog/span.h>
#include <datadog/span_config.h>
#include <datadog/tracer.h>
#include <datadog/tracer_config.h>

#include <queue>
#include <stdio.h>
#include <string>

std::string make_httpd_version() {
  ap_version_t httpd_version;
  ap_get_server_revision(&httpd_version);

  std::string version;
  version += std::to_string(httpd_version.major);
  version += ".";
  version += std::to_string(httpd_version.minor);
  version += ".";
  version += std::to_string(httpd_version.patch);

  if (httpd_version.add_string) {
    version += httpd_version.add_string;
  }
  return version;
}

namespace dd = datadog::tracing;

inline constexpr char k_active_span_key[] = "DD_ACTIVE_SPANS";

static dd::RuntimeID *k_runtime_id = nullptr;
static std::unique_ptr<datadog::tracing::Tracer> tracer = nullptr;

APLOG_USE_MODULE(ddtrace);

// Hooks
void init_tracer(apr_pool_t *, server_rec *s);
int tracer_handler(request_rec *r);
int terminate_tracer(request_rec *r);
void register_hooks(apr_pool_t *);

// Directives setter
void *init_tracer_conf(apr_pool_t *pool, server_rec *svr);
apr_status_t destroy_tracer_conf(void *ptr);

const char *set_agent_url(cmd_parms *cmd, void *cfg, const char *arg);
const char *set_service_environment(cmd_parms *cmd, void *cfg, const char *arg);
const char *set_service_version(cmd_parms *cmd, void *cfg, const char *arg);
const char *set_service_name(cmd_parms *cmd, void *cfg, const char *arg);
const char *enable_ddog(cmd_parms *cmd, void *cfg, int value);
const char *add_or_overwrite_tag(cmd_parms *cmd, void *cfg, const char *arg0,
                                 const char *arg1);
const char *enable_inbound_span(cmd_parms *cmd, void *cfg, int value);
const char *set_sampling_rate(cmd_parms *cmd, void *cfg, const char *arg);
const char *set_propagation_style(cmd_parms *cmd, void *cfg, int argc,
                                  const char *arg[]);

// clang-format off
static const command_rec ddtrace_cmds[] = {
  // Server scope
  AP_INIT_TAKE1("DatadogServiceName",          reinterpret_cast<cmd_func>(set_service_name),        NULL, RSRC_CONF, "Set service name"),
  AP_INIT_TAKE1("DatadogServiceVersion",       reinterpret_cast<cmd_func>(set_service_version),     NULL, RSRC_CONF, "Set service version"),
  AP_INIT_TAKE1("DatadogServiceEnvironment",   reinterpret_cast<cmd_func>(set_service_environment), NULL, RSRC_CONF, "Set service environment"),
  AP_INIT_TAKE1("DatadogAgentUrl",             reinterpret_cast<cmd_func>(set_agent_url),           NULL, RSRC_CONF, "Set Datadog agent URL"),
  // TODO: dd-trace-cpp does not offer a way to override the sampling rate on a trace segment at runtime.
  //       IMO, it is a hack to add a specific tag per location and use it to apply sampling rules.
  AP_INIT_TAKE1("DatadogSamplingRate",         reinterpret_cast<cmd_func>(set_sampling_rate),       NULL, RSRC_CONF, "Set Datadog sampling rate"),
  AP_INIT_TAKE_ARGV("DatadogPropagationStyle", reinterpret_cast<cmd_func>(set_propagation_style),   NULL, RSRC_CONF, "Set propagation style"),

  // Directive scope
  AP_INIT_FLAG("DatadogEnable",                reinterpret_cast<cmd_func>(enable_ddog),             NULL, ACCESS_CONF, "Enable or disable Datadog tracing module"),
  AP_INIT_FLAG("DatadogTrustInboundSpan",      reinterpret_cast<cmd_func>(enable_inbound_span),     NULL, ACCESS_CONF, "Trust inbound span headers"),
  AP_INIT_ITERATE2("DatadogAddTag",            reinterpret_cast<cmd_func>(add_or_overwrite_tag),    NULL, ACCESS_CONF, "Append tags"),

  {NULL}
};
// clang-format on

module AP_MODULE_DECLARE_DATA ddtrace_module = {
    STANDARD20_MODULE_STUFF,
    init_dir_conf,    /* Per-directory configuration handler */
    NULL,             /* Merge handler for per-directory configurations */
    init_tracer_conf, /* Per-server configuration handler */
    NULL,             /* Merge handler for per-server configurations */
    ddtrace_cmds,     /* Any directives we may have for httpd */
    register_hooks    /* Our hook registering function */
};

void register_hooks(apr_pool_t *) {
  k_runtime_id = new dd::RuntimeID(dd::RuntimeID::generate());
  ap_hook_child_init(init_tracer, NULL, NULL, APR_HOOK_MIDDLE);
  ap_hook_fixups(tracer_handler, NULL, NULL, APR_HOOK_LAST);
  ap_hook_log_transaction(terminate_tracer, NULL, NULL, APR_HOOK_REALLY_FIRST);
}

void *init_tracer_conf(apr_pool_t *pool, server_rec *s) {
  auto *conf = new dd::TracerConfig;
  apr_pool_cleanup_register(pool, (void *)conf, destroy_tracer_conf,
                            apr_pool_cleanup_null);

  conf->defaults.service = "httpd";
  conf->defaults.service_type = "server";
  conf->defaults.tags = std::unordered_map<std::string, std::string>{
      {"component", "http"},
      {"httpd.version", make_httpd_version()},
      {"httpd.virtual_host", s->is_virtual ? "true" : "false"}};
  conf->logger = std::make_shared<HttpdLogger>(s, ddtrace_module.module_index);
  conf->runtime_id = *k_runtime_id;
  return (void *)conf;
}

apr_status_t destroy_tracer_conf(void *ptr) {
  delete (dd::TracerConfig *)ptr;
  return 0;
}

const char *set_service_name(cmd_parms *cmd, void * /* cfg */,
                             const char *arg) {
  dd::TracerConfig *conf = (dd::TracerConfig *)ap_get_module_config(
      cmd->server->module_config, &ddtrace_module);

  // TODO: check context
  conf->defaults.service = arg;
  return NULL;
}
const char *set_service_version(cmd_parms *cmd, void * /* cfg */,
                                const char *arg) {
  dd::TracerConfig *conf = (dd::TracerConfig *)ap_get_module_config(
      cmd->server->module_config, &ddtrace_module);

  // TODO: check context
  conf->defaults.version = arg;
  return NULL;
}
const char *set_service_environment(cmd_parms *cmd, void * /* cfg */,
                                    const char *arg) {
  dd::TracerConfig *conf = (dd::TracerConfig *)ap_get_module_config(
      cmd->server->module_config, &ddtrace_module);

  // TODO: check context
  conf->defaults.environment = arg;
  return NULL;
}

const char *set_agent_url(cmd_parms *cmd, void * /* cfg */, const char *arg) {
  dd::TracerConfig *conf = (dd::TracerConfig *)ap_get_module_config(
      cmd->server->module_config, &ddtrace_module);

  // TODO: check context
  conf->agent.url = arg;
  return NULL;
}

const char *set_sampling_rate(cmd_parms *cmd, void * /* cfg */,
                              const char *arg) {
  dd::TracerConfig *conf = (dd::TracerConfig *)ap_get_module_config(
      cmd->server->module_config, &ddtrace_module);

  char *end = NULL;
  double rate = strtod(arg, &end);
  if (errno == ERANGE || end != 0) {
    // TODO: handle error
  }

  conf->trace_sampler.sample_rate = rate;
  return NULL;
}

const char *set_propagation_style(cmd_parms *cmd, void * /* cfg */, int argc,
                                  const char *args[]) {
  if (argc <= 0)
    return NULL;

  dd::TracerConfig *conf = (dd::TracerConfig *)ap_get_module_config(
      cmd->server->module_config, &ddtrace_module);

  std::vector<dd::PropagationStyle> propagation;

  for (int i = 0; i < argc; ++i) {
    std::string arg{args[i]};
    if (arg == "datadog") {
      propagation.emplace_back(dd::PropagationStyle::DATADOG);
    } else if (arg == "tracecontext") {
      propagation.emplace_back(dd::PropagationStyle::W3C);
    } else if (arg == "b3") {
      propagation.emplace_back(dd::PropagationStyle::B3);
    } else {
      // TODO: Log as warning instead.
      conf->logger->log_error("Unsupported propagation style");
    }
  }

  if (propagation.empty()) {
    // TODO: log nothing will be set.
  } else {
    conf->injection_styles = propagation;
    conf->extraction_styles = propagation;
  }

  return NULL;
}

const char *enable_ddog(cmd_parms * /* cmd */, void *cfg, int value) {
  DirectoryConf *dir_conf = (DirectoryConf *)cfg;
  dir_conf->enabled = (bool)value;
  return NULL;
}

const char *add_or_overwrite_tag(cmd_parms * /* cmd */, void *cfg,
                                 const char *arg0, const char *arg1) {
  if (!arg0 || !arg1)
    return NULL;

  DirectoryConf *dir_conf = (DirectoryConf *)cfg;
  dir_conf->tags[arg0] = arg1;
  return NULL;
}

const char *enable_inbound_span(cmd_parms * /* cmd */, void *cfg, int value) {
  DirectoryConf *dir_conf = (DirectoryConf *)cfg;
  dir_conf->trust_inbound_span = (bool)value;
  return NULL;
}

void init_tracer(apr_pool_t *, server_rec *s) {
  datadog::tracing::TracerConfig *config =
      (datadog::tracing::TracerConfig *)ap_get_module_config(s->module_config,
                                                             &ddtrace_module);
  if (config == nullptr) {
    ap_log_error(APLOG_MARK, APLOG_ERR, 0, s, "Missing tracer configuration");
    return;
  }

  const auto validated_config = datadog::tracing::finalize_config(*config);
  if (auto error = validated_config.if_error()) {
    config->logger->log_error(*error);
    return;
  }

  // TODO: destroy `tracer_config`
  tracer = std::make_unique<datadog::tracing::Tracer>(*validated_config);
}

apr_status_t delete_active_spans(void *data) {
  auto active_spans = (std::queue<datadog::tracing::Span> *)data;
  delete active_spans;

  return 0;
}

class HeaderReader final : public datadog::tracing::DictReader {
  apr_table_t *headers_;

public:
  HeaderReader(apr_table_t *headers) : headers_(headers) {}
  ~HeaderReader() {}

  dd::Optional<dd::StringView> lookup(dd::StringView key) const override {
    if (const char *value = apr_table_get(headers_, key.data())) {
      return value;
    };

    return dd::nullopt;
  };

  void visit(const std::function<void(dd::StringView key, dd::StringView value)>
                 &) const override{};
};

class HeaderInjector final : public datadog::tracing::DictWriter {
  apr_table_t *headers_;

public:
  HeaderInjector(apr_table_t *headers) : headers_(headers) {}
  ~HeaderInjector() {}

  void set(datadog::tracing::StringView key,
           datadog::tracing::StringView value) override {
    apr_table_set(headers_, key.data(), value.data());
  }
};

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

int tracer_handler(request_rec *r) {
  if (tracer == nullptr)
    return DECLINED;

  DirectoryConf *dir_conf =
      (DirectoryConf *)ap_get_module_config(r->per_dir_config, &ddtrace_module);
  if (dir_conf == nullptr || !dir_conf->enabled)
    return DECLINED;

  void *data = nullptr;
  apr_pool_userdata_get(&data, k_active_span_key, r->pool);
  if (data)
    return DECLINED;

  std::string resource_name{r->method};
  resource_name += " ";
  resource_name += r->uri;
  resource_name += " ";
  resource_name += r->protocol;

  datadog::tracing::SpanConfig options;
  options.name = "httpd.request";
  if (r->proxyreq != PROXYREQ_NONE) {
    options.name = "httpd.proxy";
  }
  options.resource = resource_name;
  options.tags = std::unordered_map<std::string, std::string>{
      {"http.version", protocol(r->proto_num)},
      {"http.host", r->hostname},
      {"http.method", r->method},
      {"http.url", r->unparsed_uri},
      {"http.request.content_length", std::to_string(r->clength)},
  };
  options.tags.merge(dir_conf->tags);

  if (r->useragent_ip)
    options.tags.emplace("http.client_ip", r->useragent_ip);

  if (auto user_agent = apr_table_get(r->headers_in, "User-Agent")) {
    options.tags.emplace("http.useragent", user_agent);
  }

  request_rec *req = r->main ? r->main : r;

  // Register to the request pool to have the same lifecycle as
  // the request.
  auto *active_spans = new std::queue<datadog::tracing::Span>;
  apr_pool_userdata_setn((void *)active_spans, "DD_ACTIVE_SPANS",
                         delete_active_spans, req->pool);

  dd::Span *span = nullptr;

  // In case we fail to use the inbound span, then, start a new trace
  // there is nothing we can do with it.
  if (dir_conf->trust_inbound_span) {
    auto extracted_span =
        tracer->extract_or_create_span(HeaderReader(r->headers_in), options);
    if (auto error = extracted_span.if_error()) {
      span = &active_spans->emplace(tracer->create_span(options));
      span->set_error(error->message.c_str());
    } else {
      span = &active_spans->emplace(std::move(*extracted_span));
    }
  } else {
    span = &active_spans->emplace(tracer->create_span(options));
  }

  HeaderInjector header_injector(r->headers_in);
  span->inject(header_injector);

  return DECLINED;
}

int terminate_tracer(request_rec *r) {
  auto now = std::chrono::steady_clock::now();

  request_rec *req = r->main ? r->main : r;

  void *data = nullptr;
  apr_pool_userdata_get(&data, k_active_span_key, req->pool);
  if (data == nullptr)
    return DECLINED;

  auto *active_spans = (std::queue<datadog::tracing::Span> *)data;

  if (!active_spans)
    return DECLINED;

  auto &span = active_spans->front();
  span.set_end_time(now);
  span.set_tag("http.status_code", std::to_string(r->status));
  span.set_tag("http.response.content_length", std::to_string(r->bytes_sent));

  active_spans->pop();

  return DECLINED;
}
