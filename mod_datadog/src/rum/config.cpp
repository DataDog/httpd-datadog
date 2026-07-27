#include "rum/config.h"

#include <fmt/format.h>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <cstdlib>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

#include "apr_strings.h"
#include "common_conf.h"
#include "http_log.h"
#include "mod_datadog.h"
#include "utils.h"

APLOG_USE_MODULE(datadog);

using namespace datadog::conf;

namespace {

// Identifies this integration to the stable-config reader, which uses it for
// rule-based process matching in application_monitoring.yaml. Free-form, not
// validated against a fixed set; nginx-datadog passes "nginx" here.
constexpr const char* rum_language = "httpd";

using SnippetPtr = std::unique_ptr<Snippet, decltype(&snippet_cleanup)>;

// The Agent's stable configuration, read once per configuration load and shared
// by every snippet built during it. Scoped to the configuration pool: httpd
// discards that pool when it discards the configuration, so a graceful restart
// re-reads from disk.
StableConfig* g_stable_config = nullptr;

apr_status_t release_stable_config(void*) {
  stable_config_cleanup(g_stable_config);
  g_stable_config = nullptr;
  return APR_SUCCESS;
}

// Reads the stable-configuration files on first use, then hands out the same
// parsed copy. Reading is the expensive part -- two files off disk plus YAML
// parsing -- and it does not depend on the overlay, so doing it per
// <DatadogRumSettings> block would scale the cost with the number of virtual
// hosts for no benefit.
//
// `pool` is httpd's configuration pool, whether we got here from a directive or
// from post_config, so both share one read.
StableConfig* stable_config(apr_pool_t* pool) {
  if (g_stable_config == nullptr) {
    g_stable_config = stable_config_read(rum_language, false);
    apr_pool_cleanup_register(pool, nullptr, release_stable_config,
                              apr_pool_cleanup_null);
  }
  return g_stable_config;
}

// Builds a snippet from the Agent's stable configuration. `overlay_json`, when
// non-null, is merged on top of it and wins; null means use stable config alone.
SnippetPtr make_stable_config_snippet(apr_pool_t* pool,
                                     const char* overlay_json) {
  return SnippetPtr(
      stable_config_snippet_create(stable_config(pool), overlay_json),
      snippet_cleanup);
}

// Tags every telemetry counter carries, derived from the snippet the injection
// used rather than from the directives alone -- an applicationId that came from
// stable configuration has to end up in the tags too.
std::string make_app_id_tag(const Snippet& snippet) {
  // A snippet cannot be built without an applicationId, so this is only ever
  // empty for a snippet that failed to build.
  if (snippet.application_id == nullptr) {
    return {};
  }
  return fmt::format("application_id:{}", snippet.application_id);
}

std::string make_remote_config_tag(const Snippet& snippet) {
  return snippet.remote_configuration_id != nullptr ? "remote_config_used:true"
                                                    : "remote_config_used:false";
}

std::optional<bool> parse_bool(std::string_view raw) {
  std::string value(raw);
  datadog::common::utils::to_lower(value);

  if (value == "1" || value == "true" || value == "yes" || value == "on") {
    return true;
  }
  if (value == "0" || value == "false" || value == "no" || value == "off") {
    return false;
  }
  return std::nullopt;
}

// Error code the SDK returns when there was no stable configuration to build
// from: the files were absent, or matched no rule for this process. That is the
// ordinary case for anyone not using stable configuration, so it must not be
// reported as a failure. A file that *was* there but could not be read or parsed
// keeps the generic stable-config code and is reported.
constexpr int stable_config_absent = 10;

Snippet* g_stable_config_snippet = nullptr;
bool g_enabled_by_default = false;
std::string g_stable_config_app_id_tag;
std::string g_stable_config_remote_config_tag;

apr_status_t release_stable_config_snippet(void*) {
  snippet_cleanup(g_stable_config_snippet);
  g_stable_config_snippet = nullptr;
  return APR_SUCCESS;
}

// Reads the SDK's tri-state report of DD_RUM_ENABLED as an optional.
std::optional<bool> stable_config_enabled(const Snippet& snippet) {
  switch (snippet.rum_enabled) {
    case RUM_ENABLED_TRUE:
      return true;
    case RUM_ENABLED_FALSE:
      return false;
    default:
      return std::nullopt;
  }
}

std::vector<std::string> split(const std::string& str,
                               const std::string& delimiter = ",") {
  std::vector<std::string> result;
  size_t start = 0, end;
  while ((end = str.find(delimiter, start)) != std::string::npos) {
    result.push_back(str.substr(start, end - start));
    start = end + delimiter.length();
  }
  result.push_back(str.substr(start));
  return result;
}

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
    auto value_is_array = datadog::common::utils::contains(value, ",");
    if (key == "sessionSampleRate" || key == "sessionReplaySampleRate") {
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(std::stod(value)).Move(), allocator);
    } else if (key == "trackResources" || key == "trackLongTasks" ||
               key == "trackUserInteractions") {
      auto b = (value == "true" ? true : false);
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(b).Move(), allocator);
    } else if (value_is_array) {
      rapidjson::Value array(rapidjson::kArrayType);
      for (const auto& e : split(value, ",")) {
        array.PushBack(rapidjson::Value(e.c_str(), allocator).Move(),
                       allocator);
      }
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    array.Move(), allocator);
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

const char* enable_rum_ddog(cmd_parms* /* cmd */, void* cfg, int value) {
  auto* dir_conf = static_cast<Directory*>(cfg);
  dir_conf->rum.enabled = static_cast<bool>(value);
  return NULL;
}

const char* set_rum_option(cmd_parms* cmd, void* cfg, int argc,
                           const char* argv[]) {
  if (cmd->directive->parent == nullptr ||
      std::string_view(cmd->directive->parent->directive) !=
          "<DatadogRumSettings") {
    return apr_pstrcat(cmd->pool, cmd->cmd->name,
                       " cannot occur outside <DatadogRumSettings> section",
                       NULL);
  }

  if (argc < 2) {
    return "DatadogRumOption requires at least 2 arguments.";
  }

  // NOTE(@dmehala): Workaround -> For argv > 2 join all values with ","
  std::string value = argv[1];
  for (int i = 2; i < argc; ++i) {
    value += fmt::format(",{}", argv[i]);
  }

  auto* dir_conf = static_cast<Directory*>(cfg);
  dir_conf->rum.config.emplace(argv[0], value);
  return NULL;
}

const char* datadog_rum_settings_section(cmd_parms* cmd, void* cfg,
                                         const char* arg) {
  const char* endp = ap_strrchr_c(arg, '>');
  if (endp == nullptr) {
    return apr_pstrcat(cmd->pool, cmd->cmd->name,
                       "> directive missing closing '>'", nullptr);
  }

  std::string version = "v6";
  const char* left_quote = ap_strchr_c(arg, '"');
  if (left_quote) {
    const char* right_quote = ap_strchr_c(left_quote + 1, '"');
    if (!right_quote) {
      return apr_pstrcat(
          cmd->pool, cmd->cmd->name,
          "> version missing opening or closing double quote '\"'", nullptr);
    }

    std::string parsed_version(left_quote + 1, right_quote - left_quote - 1);
    if (!parsed_version.empty()) {
      version = parsed_version;
    }
  }

  if (version.length() < 2 ||
      !std::all_of(version.begin() + 1, version.end(),
                   [](char c) { return std::isdigit(c); })) {
    return apr_pstrcat(cmd->pool, cmd->cmd->name, "> version format error",
                       nullptr);
  }

  auto& dir_conf = *static_cast<Directory*>(cfg);
  dir_conf.rum.version = version;
  const char* err =
      ap_walk_config(cmd->directive->first_child, cmd, cmd->context);
  if (err != nullptr) {
    return err;
  }

  const auto json_config =
      make_rum_json_config(dir_conf.rum.version, dir_conf.rum.config);
  if (json_config.empty()) {
    return "failed to generate the RUM SDK script";
  }

  // The directives are an overlay: the SDK merges them on top of the Agent's
  // stable configuration, and they win on conflict. With no stable
  // configuration present this behaves exactly as the previous
  // snippet_create_from_json call did.
  auto snippet = make_stable_config_snippet(cmd->pool, json_config.c_str());
  if (snippet->error_code != 0) {
    return apr_psprintf(cmd->pool,
                        "Failed to initialize RUM SDK injection: %s",
                        snippet->error_message);
  }

  // Tags come from the merged result, not from the directives: a block that
  // overrides only the sample rate still injects the applicationId that stable
  // configuration supplied, and its telemetry has to say so.
  dir_conf.rum.app_id_tag = make_app_id_tag(*snippet);
  dir_conf.rum.remote_config_tag = make_remote_config_tag(*snippet);
  dir_conf.rum.snippet = snippet.release();

  return NULL;
}

namespace datadog::rum::conf {

Resolved resolve(const Directory& dir) {
  Resolved out;

  // A <DatadogRumSettings> block in scope (or inherited from a parent) wins,
  // else use the one built from stable configuration alone -- together with the
  // tags that belong to whichever snippet won.
  if (dir.snippet != nullptr) {
    out.snippet = dir.snippet;
    out.app_id_tag = dir.app_id_tag;
    out.remote_config_tag = dir.remote_config_tag;
  } else {
    out.snippet = g_stable_config_snippet;
    out.app_id_tag = g_stable_config_app_id_tag;
    out.remote_config_tag = g_stable_config_remote_config_tag;
  }

  // A DatadogRum directive in scope decides; otherwise fall back to the
  // process-wide default, which stable configuration can turn on or off.
  out.enabled = dir.enabled.value_or(g_enabled_by_default);

  return out;
}

void init_stable_config(server_rec* s, apr_pool_t* pconf) {
  // Rebuild from scratch: post_config runs again on graceful restart, and the
  // on-disk stable configuration may have changed since the last load.
  release_stable_config_snippet(nullptr);
  g_enabled_by_default = false;
  g_stable_config_app_id_tag.clear();
  g_stable_config_remote_config_tag.clear();

  std::optional<bool> configured_enabled;

  auto snippet = make_stable_config_snippet(pconf, nullptr);
  if (snippet->error_code == 0) {
    configured_enabled = stable_config_enabled(*snippet);
    g_stable_config_app_id_tag = make_app_id_tag(*snippet);
    g_stable_config_remote_config_tag = make_remote_config_tag(*snippet);
    g_stable_config_snippet = snippet.release();
    apr_pool_cleanup_register(pconf, nullptr, release_stable_config_snippet,
                              apr_pool_cleanup_null);
    ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, s,
                 "httpd-datadog: RUM configured from stable configuration");
  } else if (snippet->error_code != stable_config_absent) {
    // stable_config_absent means no application_monitoring.yaml, which is the
    // ordinary case and not worth reporting.
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                 "httpd-datadog: ignoring RUM stable configuration: %s",
                 snippet->error_message);
  }

  // Precedence for the default, highest first: DD_RUM_ENABLED in the process
  // environment, then DD_RUM_ENABLED in stable configuration, then "on exactly
  // when stable configuration supplied a snippet" -- so stable configuration
  // alone is enough to turn RUM on, and can equally turn it off while leaving
  // its RUM keys in place.
  if (const char* raw = std::getenv("DD_RUM_ENABLED");
      raw != nullptr && raw[0] != '\0') {
    const auto parsed = parse_bool(raw);
    if (parsed.has_value()) {
      configured_enabled = parsed;
    } else {
      ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                   "httpd-datadog: unrecognized DD_RUM_ENABLED value '%s'; "
                   "expected true/false/1/0/yes/no/on/off",
                   raw);
    }
  }

  g_enabled_by_default =
      configured_enabled.value_or(g_stable_config_snippet != nullptr);

  if (g_enabled_by_default && g_stable_config_snippet == nullptr) {
    // Only a warning, not an error: a <DatadogRumSettings> block elsewhere in
    // the configuration may still supply a snippet for some scopes. Reachable
    // only via an explicit DD_RUM_ENABLED, since the derived default implies a
    // snippet.
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                 "httpd-datadog: DD_RUM_ENABLED is true but stable "
                 "configuration provided no RUM snippet");
  }
}

void merge_directory_configuration(Directory& out, const Directory& parent,
                                   const Directory& child) {
  // If child explicitly set enabled, use child's value; otherwise inherit from
  // parent
  out.enabled = child.enabled.has_value() ? child.enabled : parent.enabled;
  out.snippet = child.snippet ? child.snippet : parent.snippet;
  out.app_id_tag =
      child.app_id_tag.empty() ? parent.app_id_tag : child.app_id_tag;
  out.remote_config_tag = child.remote_config_tag.empty()
                              ? parent.remote_config_tag
                              : child.remote_config_tag;

  return;
}
}  // namespace datadog::rum::conf
