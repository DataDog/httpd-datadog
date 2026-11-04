#include "rum/config.h"

#include <fmt/format.h>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <cmath>
#include <cstdlib>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

#include "apr_strings.h"
#include "common_conf.h"
#include "http_log.h"
#include "mod_datadog.h"
#include "utils.h"

APLOG_USE_MODULE(datadog);

using namespace datadog::conf;

namespace {
// Process name used to match stable configuration rules.
constexpr const char* rum_language = "httpd";

// Error code when there is no stable configuration. This is not an error.
constexpr int stable_config_absent = 10;

using SnippetPtr = std::unique_ptr<Snippet, decltype(&snippet_cleanup)>;
using StableConfigPtr =
    std::unique_ptr<StableConfig, decltype(&stable_config_cleanup)>;

// Read once per configuration load. Released by init_stable_config().
StableConfigPtr g_stable_config{nullptr, &stable_config_cleanup};

// Built from stable configuration alone, by init_stable_config().
SnippetPtr g_stable_config_snippet{nullptr, &snippet_cleanup};
std::string g_stable_config_app_id_tag;
std::string g_stable_config_remote_config_tag;
std::optional<bool> g_env_rum_enabled;

StableConfig* stable_config() {
  if (!g_stable_config) {
    g_stable_config.reset(stable_config_read(rum_language, false));
  }
  return g_stable_config.get();
}

// `overlay_json` wins over stable configuration. Null means no overlay.
SnippetPtr make_stable_config_snippet(const char* overlay_json) {
  return SnippetPtr(stable_config_snippet_create(stable_config(), overlay_json),
                    snippet_cleanup);
}

std::string make_app_id_tag(const Snippet& snippet) {
  // Null when stable configuration disables RUM without an applicationId.
  if (snippet.application_id == nullptr) {
    return {};
  }
  return fmt::format("application_id:{}", snippet.application_id);
}

std::string make_remote_config_tag(const Snippet& snippet) {
  return snippet.remote_configuration_id != nullptr
             ? "remote_config_used:true"
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

// Nullopt when DD_RUM_ENABLED is unset, empty or invalid.
std::optional<bool> env_rum_enabled(server_rec* base_server) {
  const char* raw = std::getenv("DD_RUM_ENABLED");
  if (raw == nullptr || raw[0] == '\0') {
    return std::nullopt;
  }
  const auto parsed = parse_bool(raw);
  if (!parsed.has_value()) {
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, base_server,
                 "httpd-datadog: unrecognized DD_RUM_ENABLED value '%s'; "
                 "expected true/false/1/0/yes/no/on/off",
                 raw);
  }
  return parsed;
}

// DD_RUM_ENABLED from stable configuration.
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

bool valid_version(const std::string& version) {
  return version.size() >= 2 && version.front() == 'v' &&
         std::all_of(version.begin() + 1, version.end(), [](char character) {
           return character >= '0' && character <= '9';
         });
}

double parse_sample_rate(const std::string& key, const std::string& value) {
  size_t consumed = 0;
  double rate;
  try {
    rate = std::stod(value, &consumed);
  } catch (const std::exception&) {
    throw std::invalid_argument(fmt::format("{} must be a number", key));
  }
  if (value.find_first_not_of(" \t\r\n\f\v", consumed) != std::string::npos ||
      !std::isfinite(rate)) {
    throw std::invalid_argument(
        fmt::format("{} must be a complete, finite number", key));
  }
  return rate;
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
  const int major_version = std::stoi(std::string(config_version.substr(1)));
  doc.AddMember("majorVersion", rapidjson::Value(major_version), allocator);

  rapidjson::Value rum(rapidjson::kObjectType);
  for (const auto& [key, value] : config) {
    auto value_is_array = datadog::common::utils::contains(value, ",");
    if (key == "sessionSampleRate" || key == "sessionReplaySampleRate") {
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(parse_sample_rate(key, value)).Move(),
                    allocator);
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

  if (!valid_version(version)) {
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

  std::string json_config;
  try {
    json_config =
        make_rum_json_config(dir_conf.rum.version, dir_conf.rum.config);
  } catch (const std::exception& error) {
    return apr_psprintf(cmd->pool, "Invalid RUM settings: %s", error.what());
  }
  if (json_config.empty()) {
    return "failed to generate the RUM SDK script";
  }

  // Options of the section win over stable configuration.
  auto snippet = make_stable_config_snippet(json_config.c_str());
  if (snippet->error_code != 0) {
    // Invalid stable configuration must not stop httpd: use the section alone.
    SnippetPtr fallback(snippet_create_from_json(json_config.c_str()),
                        snippet_cleanup);
    if (fallback->error_code != 0) {
      return apr_psprintf(cmd->pool,
                          "Failed to initialize RUM SDK injection: %s",
                          fallback->error_message);
    }
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, cmd->server,
                 "httpd-datadog: ignoring RUM stable configuration for this "
                 "<DatadogRumSettings> block: %s",
                 snippet->error_message);
    snippet = std::move(fallback);

    // snippet_create_from_json does not report the ids: read the options.
    const auto& options = dir_conf.rum.config;
    if (auto it = options.find("applicationId"); it != options.end()) {
      dir_conf.rum.app_id_tag = fmt::format("application_id:{}", it->second);
    }
    dir_conf.rum.remote_config_tag = options.count("remoteConfigurationId")
                                         ? "remote_config_used:true"
                                         : "remote_config_used:false";
  } else {
    dir_conf.rum.app_id_tag = make_app_id_tag(*snippet);
    dir_conf.rum.remote_config_tag = make_remote_config_tag(*snippet);
  }

  dir_conf.rum.snippet = std::move(snippet);

  return NULL;
}

namespace datadog::rum::conf {

ResolvedConfig resolve_configuration(const Directory& dir) {
  ResolvedConfig out;

  // A <DatadogRumSettings> section in scope wins over stable configuration.
  if (dir.snippet != nullptr) {
    out.snippet = dir.snippet.get();
    out.app_id_tag = dir.app_id_tag;
    out.remote_config_tag = dir.remote_config_tag;
  } else {
    out.snippet = g_stable_config_snippet.get();
    out.app_id_tag = g_stable_config_app_id_tag;
    out.remote_config_tag = g_stable_config_remote_config_tag;
  }
  if (out.snippet == nullptr) {
    return out;
  }

  // Precedence, highest first: DD_RUM_ENABLED=false in stable configuration,
  // DatadogRum, DD_RUM_ENABLED in the environment, DD_RUM_ENABLED in stable
  // configuration, then on if stable configuration gave a snippet.
  const auto stable_enabled = stable_config_enabled(*out.snippet);
  const bool killed = stable_enabled == false;
  const bool default_enabled = g_env_rum_enabled.value_or(
      stable_enabled.value_or(g_stable_config_snippet != nullptr));
  out.enabled = !killed && dir.enabled.value_or(default_enabled);

  return out;
}

void init_stable_config(server_rec* base_server) {
  g_stable_config_snippet.reset();
  g_stable_config_app_id_tag.clear();
  g_stable_config_remote_config_tag.clear();
  g_env_rum_enabled = env_rum_enabled(base_server);

  auto snippet = make_stable_config_snippet(nullptr);
  // All <DatadogRumSettings> sections are built by now.
  g_stable_config.reset();

  if (snippet->error_code == 0) {
    ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, base_server,
                 "httpd-datadog: RUM %s stable configuration",
                 snippet->rum_enabled == RUM_ENABLED_FALSE ? "disabled by"
                                                           : "configured from");
    g_stable_config_app_id_tag = make_app_id_tag(*snippet);
    g_stable_config_remote_config_tag = make_remote_config_tag(*snippet);
    g_stable_config_snippet = std::move(snippet);
  } else if (snippet->error_code != stable_config_absent) {
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, base_server,
                 "httpd-datadog: ignoring RUM stable configuration: %s",
                 snippet->error_message);
  }

  if (g_env_rum_enabled == true && g_stable_config_snippet == nullptr) {
    // Only a warning: a <DatadogRumSettings> section may still give a snippet.
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, base_server,
                 "httpd-datadog: DD_RUM_ENABLED is true but stable "
                 "configuration provided no RUM snippet");
  }
}

void merge_directory_configuration(Directory& out, const Directory& parent,
                                   const Directory& child) {
  // If child explicitly set enabled, use child's value; otherwise inherit from
  // parent
  out.enabled = child.enabled.has_value() ? child.enabled : parent.enabled;
  // The tags describe the snippet, so they are inherited with it.
  const auto& source = child.snippet ? child : parent;
  out.snippet = source.snippet;
  out.app_id_tag = source.app_id_tag;
  out.remote_config_tag = source.remote_config_tag;

  return;
}
}  // namespace datadog::rum::conf
