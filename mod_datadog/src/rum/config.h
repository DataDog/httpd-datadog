#pragma once

#include "http_core.h"
#include "injectbrowsersdk.h"

inline const char* rum_filter_name = "mod_rum_inject";

const char* enable_rum_ddog(cmd_parms* cmd, void* cfg, int value);
const char* set_rum_option(cmd_parms* cmd, void* cfg, int argc,
                           const char* argv[]);
const char* datadog_rum_settings_section(cmd_parms* cmd, void* cfg,
                                         const char* arg);

// clang-format off
#define RUM_MODULE_CMDS \
  AP_INIT_FLAG("DatadogRum", reinterpret_cast<cmd_func>(enable_rum_ddog), NULL, RSRC_CONF | ACCESS_CONF, "Enable or disable Datadog RUM module"), \
  AP_INIT_RAW_ARGS("<DatadogRumSettings", reinterpret_cast<cmd_func>(datadog_rum_settings_section), NULL, RSRC_CONF | ACCESS_CONF, "Container for Datadog RUM settings"), \
  AP_INIT_TAKE_ARGV("DatadogRumOption", reinterpret_cast<cmd_func>(set_rum_option), NULL, RSRC_CONF | ACCESS_CONF, "Set options on the RUM SDK"),
// clang-format on

namespace datadog::rum::conf {

struct Directory final {
  bool enabled = false;
  Snippet* snippet = nullptr;
  std::unordered_map<std::string, std::string> config;

  ~Directory() {
    if (snippet != nullptr) {
      snippet_cleanup(snippet);
    }
  }
};

void merge_directory_configuration(Directory& out, const Directory& parent,
                                   const Directory& child);

}  // namespace datadog::rum::conf
