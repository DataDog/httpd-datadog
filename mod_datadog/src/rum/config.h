#pragma once

#include <optional>
#include <string>
#include <string_view>
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

// Everything the response filter needs, resolved from a directory configuration
// and the process-wide stable configuration.
//
// The fallbacks belong together: a scope with no <DatadogRumSettings> of its own
// injects the stable-configuration snippet, and its telemetry has to carry that
// snippet's identifiers. Resolving snippet and tags in separate places is how
// they came apart -- the filter picked up the snippet and left the tags empty.
struct Resolved final {
  bool enabled = false;
  // Never freed by the caller: owned by either the Directory or the
  // process-wide stable configuration.
  Snippet* snippet = nullptr;
  // Both are empty only when `snippet` is nullptr: a snippet cannot be built
  // without an applicationId.
  std::string_view app_id_tag;
  std::string_view remote_config_tag;
};

Resolved resolve(const Directory& dir);

// Reads the Agent's stable-configuration files (local + fleet-managed
// application_monitoring.yaml) and caches the resulting snippet, the identifiers
// that go with it, and whether RUM should be on by default.
//
// Call once per configuration load, from post_config; `pconf` scopes the cached
// snippet to that load. Deliberately not done during directory-config merging
// the way nginx-datadog does it: httpd merges per-directory configuration inside
// ap_location_walk, which runs *per request*, so building the snippet there
// would read YAML off disk on every request. post_config also re-runs on
// graceful restart, so the cache cannot go stale.
void init_stable_config(server_rec* s, apr_pool_t* pconf);

}  // namespace datadog::rum::conf
