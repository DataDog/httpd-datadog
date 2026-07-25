#pragma once

#include <optional>
#include <string>
#include <unordered_map>

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
  std::optional<bool> enabled;  // nullopt = inherit from parent
  Snippet* snippet = nullptr;
  std::string version;
  std::unordered_map<std::string, std::string> config;
  std::string app_id_tag;
  std::string remote_config_tag;

  ~Directory() {
    if (snippet != nullptr) {
      snippet_cleanup(snippet);
    }
  }
};

void merge_directory_configuration(Directory& out, const Directory& parent,
                                   const Directory& child);

// Reads the Agent's stable-configuration files (local + fleet-managed
// application_monitoring.yaml) and caches the resulting snippet, plus whether
// RUM should be on by default, for the whole process.
//
// Call once per configuration load, from post_config. Deliberately not done
// during directory-config merging the way nginx-datadog does it: httpd merges
// per-directory configuration inside ap_location_walk, which runs *per request*,
// so building the snippet there would read YAML off disk on every request.
// post_config also re-runs on graceful restart, so the cache cannot go stale.
void init_stable_config(server_rec* s);

// Snippet built from stable configuration alone, or nullptr when stable
// configuration is absent or unusable. Shared and read-only; never freed.
Snippet* stable_config_snippet();

// Whether RUM injection applies where no DatadogRum directive said either way.
// Honours DD_RUM_ENABLED; otherwise true when a stable-config snippet exists, so
// stable configuration alone is enough to turn RUM on.
bool enabled_by_default();

}  // namespace datadog::rum::conf
