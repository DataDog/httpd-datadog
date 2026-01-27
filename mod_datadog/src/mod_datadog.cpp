#include <apr_uri.h>
#include <datadog/runtime_id.h>
#include <datadog/tracer.h>
#include <fmt/core.h>
#include <http_core.h>
#include <http_log.h>
#include <http_protocol.h>
#include <http_request.h>

#include <atomic>
#include <memory>
#include <string>

#include "common_conf.h"
#include "version.h"
#if defined(HTTPD_DD_RUM)
#include "rum/config.h"
#include "rum/filter.h"
#else
#define RUM_MODULE_CMDS
#endif
#include <datadog/version.h>

#include "tracing/conf.h"
#include "tracing/hooks.h"
#include "utils.h"

namespace dd = datadog::tracing;

static std::atomic<bool> g_log_module_status = true;
static std::unique_ptr<dd::RuntimeID> g_runtime_id = nullptr;
static std::unique_ptr<dd::Tracer> g_tracer = nullptr;

APLOG_USE_MODULE(datadog);

void* init_module_conf(apr_pool_t*, server_rec*);
apr_status_t destroy_module_conf(void*);

// Hooks
int on_post_config(apr_pool_t*, apr_pool_t*, apr_pool_t*, server_rec*);
void on_child_init(apr_pool_t*, server_rec*);
apr_status_t on_child_exit(void*);
int on_fixups(request_rec*);
int on_log_transaction(request_rec*);
void register_hooks(apr_pool_t*);

// Directives setter
const char* set_agent_url(cmd_parms*, void*, const char*);
const char* set_service_environment(cmd_parms*, void*, const char*);
const char* set_service_version(cmd_parms*, void*, const char*);
const char* set_service_name(cmd_parms*, void*, const char*);
const char* enable_tracing(cmd_parms*, void*, int);
const char* add_or_overwrite_tag(cmd_parms*, void*, const char*, const char*);
const char* enable_inbound_span(cmd_parms*, void*, int);
const char* set_sampling_rate(cmd_parms*, void*, const char*);
const char* set_propagation_style(cmd_parms*, void*, int, const char*[]);

// clang-format off
static const command_rec datadog_commands[] = {
  // Server scope
  AP_INIT_TAKE1("DatadogServiceName",          reinterpret_cast<cmd_func>(set_service_name),        NULL, RSRC_CONF, "Set service name"),
  AP_INIT_TAKE1("DatadogServiceVersion",       reinterpret_cast<cmd_func>(set_service_version),     NULL, RSRC_CONF, "Set service version"),
  AP_INIT_TAKE1("DatadogServiceEnvironment",   reinterpret_cast<cmd_func>(set_service_environment), NULL, RSRC_CONF, "Set service environment"),
  AP_INIT_TAKE1("DatadogAgentUrl",             reinterpret_cast<cmd_func>(set_agent_url),           NULL, RSRC_CONF, "Set Datadog agent URL"),
  AP_INIT_TAKE1("DatadogSamplingRate",         reinterpret_cast<cmd_func>(set_sampling_rate),       NULL, RSRC_CONF, "Set Datadog sampling rate"),
  AP_INIT_TAKE_ARGV("DatadogPropagationStyle", reinterpret_cast<cmd_func>(set_propagation_style),   NULL, RSRC_CONF, "Set propagation style"),

  // Server and Directive scope
  AP_INIT_FLAG("DatadogTracing",               reinterpret_cast<cmd_func>(enable_tracing),          NULL, RSRC_CONF | ACCESS_CONF, "Enable or disable Datadog tracing module"),
  AP_INIT_FLAG("DatadogTrustInboundSpan",      reinterpret_cast<cmd_func>(enable_inbound_span),     NULL, RSRC_CONF | ACCESS_CONF, "Trust inbound span headers"),
  AP_INIT_ITERATE2("DatadogAddTag",            reinterpret_cast<cmd_func>(add_or_overwrite_tag),    NULL, RSRC_CONF | ACCESS_CONF, "Append tags"),

  RUM_MODULE_CMDS

  {NULL}
};
// clang-format on

module AP_MODULE_DECLARE_DATA datadog_module = {
    STANDARD20_MODULE_STUFF,
    datadog::conf::init_dir_conf,  /* Per-directory configuration handler */
    datadog::conf::merge_dir_conf, /* Merge handler for per-directory
                                      configurations */
    init_module_conf,              /* Per-server configuration handler */
    NULL,             /* Merge handler for per-server configurations */
    datadog_commands, /* Any directives we may have for httpd */
    register_hooks    /* Our hook registering function */
};

#if defined(HTTPD_DD_RUM)
static void insert_datadog_filters(request_rec* r) {
  ap_add_output_filter(rum_filter_name, NULL, r, r->connection);
}
#endif

void register_hooks(apr_pool_t*) {
  g_runtime_id = std::make_unique<dd::RuntimeID>(dd::RuntimeID::generate());
  ap_hook_post_config(on_post_config, NULL, NULL, APR_HOOK_MIDDLE);
  ap_hook_child_init(on_child_init, NULL, NULL, APR_HOOK_MIDDLE);
  ap_hook_fixups(on_fixups, NULL, NULL, APR_HOOK_LAST);
  ap_hook_log_transaction(on_log_transaction, NULL, NULL,
                          APR_HOOK_REALLY_FIRST);

#if defined(HTTPD_DD_RUM)
  ap_hook_insert_filter(insert_datadog_filters, NULL, NULL, APR_HOOK_MIDDLE);
  ap_register_output_filter(rum_filter_name, rum_output_filter, NULL,
                            AP_FTYPE_RESOURCE);
#endif
}

int on_post_config(apr_pool_t*, apr_pool_t*, apr_pool_t*, server_rec* s) {
  if (!g_log_module_status) {
    return OK;
  }

  g_log_module_status = false;

  ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, s, "httpd-datadog status: enabled");
  ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, s, "%s",
               mod_datadog_version_string.data());
  ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, s, "httpd-datadog products:");
  ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, s, "- tracing: dd-trace-cpp@%s",
               datadog::tracing::tracer_version);
  return OK;
}

void* init_module_conf(apr_pool_t* pool, server_rec* s) {
  auto* module_conf = new datadog::conf::Module;
  auto* opaque_ptr = static_cast<void*>(module_conf);
  apr_pool_cleanup_register(pool, opaque_ptr, destroy_module_conf,
                            apr_pool_cleanup_null);

  datadog::tracing::conf::init(module_conf->tracing, *g_runtime_id, s,
                               &datadog_module);

  return opaque_ptr;
}

apr_status_t destroy_module_conf(void* ptr) {
  delete static_cast<datadog::conf::Module*>(ptr);
  return 0;
}

const char* set_service_name(cmd_parms* cmd, void* /* cfg */, const char* arg) {
  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(cmd->server->module_config, &datadog_module));

  module_conf->tracing.service = arg;
  return NULL;
}
const char* set_service_version(cmd_parms* cmd, void* /* cfg */,
                                const char* arg) {
  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(cmd->server->module_config, &datadog_module));

  module_conf->tracing.version = arg;
  return NULL;
}
const char* set_service_environment(cmd_parms* cmd, void* /* cfg */,
                                    const char* arg) {
  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(cmd->server->module_config, &datadog_module));

  module_conf->tracing.environment = arg;
  return NULL;
}

const char* set_agent_url(cmd_parms* cmd, void* /* cfg */, const char* arg) {
  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(cmd->server->module_config, &datadog_module));

  apr_uri_t uri;
  apr_status_t status = apr_uri_parse(cmd->pool, arg, &uri);
  if (status != 0 || uri.is_initialized == 0 || uri.scheme == nullptr ||
      uri.hostinfo == nullptr) {
    char* err_msg = new char[256];
    fmt::format_to_n(err_msg, 256, "{}: failed to parse \"{}\" URL",
                     cmd->directive->directive, arg);
    return err_msg;
  }

  module_conf->tracing.agent.url = arg;
  return NULL;
}

const char* set_sampling_rate(cmd_parms* cmd, void* /* cfg */,
                              const char* arg) {
  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(cmd->server->module_config, &datadog_module));

  char* end = NULL;

  double rate = strtod(arg, &end);
  if (errno == ERANGE || *end != 0) {
    char* err_msg = new char[256];
    fmt::format_to_n(err_msg, 256, "{}: could not parse \"{}\" input",
                     cmd->directive->directive, arg);
    return err_msg;
  }

  if (rate < 0.0 || rate > 1.0) {
    char* err_msg = new char[256];
    fmt::format_to_n(err_msg, 256,
                     "{}: \"{}\" input is not in the [0;1] expected range",
                     cmd->directive->directive, arg);
    return err_msg;
  }

  module_conf->tracing.trace_sampler.sample_rate = rate;
  return NULL;
}

const char* set_propagation_style(cmd_parms* cmd, void* /* cfg */, int argc,
                                  const char* args[]) {
  if (argc <= 0) {
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, cmd->server,
                 "%s: empty input. This directive is ignored and default "
                 "propagation style will be used",
                 cmd->directive->directive);
    return NULL;
  }

  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(cmd->server->module_config, &datadog_module));

  std::vector<dd::PropagationStyle> propagation;

  for (int i = 0; i < argc; ++i) {
    std::string arg{args[i]};
    datadog::common::utils::to_lower(arg);

    if (arg == "datadog") {
      propagation.emplace_back(dd::PropagationStyle::DATADOG);
    } else if (arg == "tracecontext") {
      propagation.emplace_back(dd::PropagationStyle::W3C);
    } else if (arg == "b3") {
      propagation.emplace_back(dd::PropagationStyle::B3);
    } else {
      char* err_msg = new char[256];
      fmt::format_to_n(err_msg, 256,
                       "{}: \"{}\" is not a supported propagation style. Only "
                       "\"datadog\", \"tracecontext\" and \"b3\" are valid "
                       "propagation styles",
                       cmd->directive->directive, arg);
      return err_msg;
    }
  }

  module_conf->tracing.injection_styles = propagation;
  module_conf->tracing.extraction_styles = propagation;

  return NULL;
}

const char* enable_tracing(cmd_parms* /* cmd */, void* cfg, int value) {
  auto* dir_conf = static_cast<datadog::conf::Directory*>(cfg);
  dir_conf->tracing_enabled = value != 0;
  return NULL;
}

const char* add_or_overwrite_tag(cmd_parms* /* cmd */, void* cfg,
                                 const char* arg0, const char* arg1) {
  if (!arg0 || !arg1) return NULL;

  auto* dir_conf = static_cast<datadog::conf::Directory*>(cfg);
  dir_conf->tags.emplace(arg0, arg1);

  return NULL;
}

const char* enable_inbound_span(cmd_parms* /* cmd */, void* cfg, int value) {
  auto* dir_conf = static_cast<datadog::conf::Directory*>(cfg);
  dir_conf->trust_inbound_span = value != 0;
  return NULL;
}

void init_tracer(datadog::tracing::TracerConfig& tracer_conf) {
  const bool is_service_set = tracer_conf.service.has_value();
  if (!is_service_set) {
    // NOTE: Could use s->process->short_name for the default service name.
    tracer_conf.service = "httpd";
  }

  auto validated_config = datadog::tracing::finalize_config(tracer_conf);
  if (auto error = validated_config.if_error()) {
    tracer_conf.logger->log_error(*error);
    return;
  }

  if (!is_service_set) {
    // Trick: change the service name origin to default as "httpd" is the
    // default value when no service name has been provided.
    auto& service_name_metadata =
        validated_config->metadata[datadog::tracing::ConfigName::SERVICE_NAME];
    service_name_metadata.origin =
        datadog::tracing::ConfigMetadata::Origin::DEFAULT;
  }

  g_tracer = std::make_unique<datadog::tracing::Tracer>(*validated_config);
}

void on_child_init(apr_pool_t* pool, server_rec* s) {
  auto* module_conf = static_cast<datadog::conf::Module*>(
      ap_get_module_config(s->module_config, &datadog_module));
  if (module_conf == nullptr) {
    ap_log_error(APLOG_MARK, APLOG_ERR, 0, s, "Missing datadog configuration");
    return;
  }

  init_tracer(module_conf->tracing);

  // Register cleanup hook to prevent crashes during shutdown
  apr_pool_cleanup_register(pool, nullptr, on_child_exit,
                            apr_pool_cleanup_null);
}

apr_status_t on_child_exit(void*) {
  // Explicitly clean up global objects to prevent crashes during process
  // shutdown
  g_tracer.reset();
  g_runtime_id.reset();
  return APR_SUCCESS;
}

int on_fixups(request_rec* r) {
  if (g_tracer == nullptr) return DECLINED;
  return datadog::tracing::on_fixups(r, *g_tracer, &datadog_module);
}

int on_log_transaction(request_rec* r) {
  return datadog::tracing::on_log_transaction(r, &datadog_module);
}
