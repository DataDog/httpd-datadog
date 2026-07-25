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

// Builds a snippet from the Agent's stable configuration. `overlay_json`, when
// non-null, is merged on top of it and wins; null means use stable config alone.
SnippetPtr make_stable_config_snippet(const char* overlay_json) {
  return SnippetPtr(
      snippet_create_from_stable_config(rum_language, false, overlay_json),
      snippet_cleanup);
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

// Error code the SDK returns for "no stable-config entries found", i.e. no
// application_monitoring.yaml was present. That is the ordinary case for anyone
// not using stable configuration, so it must not be reported as a failure.
constexpr int stable_config_absent = 6;

Snippet* g_stable_config_snippet = nullptr;
bool g_enabled_by_default = false;

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

  if (auto it_app_id = dir_conf.rum.config.find("applicationId");
      it_app_id != dir_conf.rum.config.end()) {
    dir_conf.rum.app_id_tag =
        fmt::format("application_id:{}", it_app_id->second);
  }

  dir_conf.rum.remote_config_tag =
      dir_conf.rum.config.count("remoteConfigurationId")
          ? "remote_config_used:true"
          : "remote_config_used:false";

  const auto json_config =
      make_rum_json_config(dir_conf.rum.version, dir_conf.rum.config);
  if (json_config.empty()) {
    return "failed to generate the RUM SDK script";
  }

  // The directives are an overlay: the SDK merges them on top of the Agent's
  // stable configuration, and they win on conflict. With no stable
  // configuration present this behaves exactly as the previous
  // snippet_create_from_json call did.
  auto snippet = make_stable_config_snippet(json_config.c_str());
  if (snippet == nullptr || snippet->error_code != 0) {
    return apr_psprintf(
        cmd->pool, "Failed to initialize RUM SDK injection: %s",
        snippet ? snippet->error_message : "snippet allocation failed");
  }

  dir_conf.rum.snippet = snippet.release();

  return NULL;
}

namespace datadog::rum::conf {

Snippet* stable_config_snippet() { return g_stable_config_snippet; }

bool enabled_by_default() { return g_enabled_by_default; }

void init_stable_config(server_rec* s) {
  // Rebuild from scratch: post_config runs again on graceful restart, and the
  // on-disk stable configuration may have changed since the last load.
  g_stable_config_snippet = nullptr;
  g_enabled_by_default = false;

  auto snippet = make_stable_config_snippet(nullptr);
  if (snippet == nullptr) {
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                 "httpd-datadog: RUM snippet allocation failed while reading "
                 "stable configuration");
  } else if (snippet->error_code == stable_config_absent) {
    // No application_monitoring.yaml. Normal; nothing to report.
  } else if (snippet->error_code != 0) {
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                 "httpd-datadog: ignoring RUM stable configuration: %s",
                 snippet->error_message);
  } else {
    g_stable_config_snippet = snippet.release();
    ap_log_error(APLOG_MARK, APLOG_NOTICE, 0, s,
                 "httpd-datadog: RUM configured from stable configuration");
  }

  // DD_RUM_ENABLED, when set to something recognised, decides the default.
  // Otherwise RUM defaults on exactly when stable configuration supplied a
  // snippet, so stable configuration alone is enough and no directive or
  // environment variable is required.
  const char* raw = std::getenv("DD_RUM_ENABLED");
  if (raw == nullptr || raw[0] == '\0') {
    g_enabled_by_default = (g_stable_config_snippet != nullptr);
    return;
  }

  const auto parsed = parse_bool(raw);
  if (!parsed.has_value()) {
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                 "httpd-datadog: unrecognized DD_RUM_ENABLED value '%s'; "
                 "expected true/false/1/0/yes/no/on/off",
                 raw);
    g_enabled_by_default = (g_stable_config_snippet != nullptr);
    return;
  }

  if (*parsed && g_stable_config_snippet == nullptr) {
    // Only a warning, not an error: a <DatadogRumSettings> block elsewhere in
    // the configuration may still supply a snippet for some scopes.
    ap_log_error(APLOG_MARK, APLOG_WARNING, 0, s,
                 "httpd-datadog: DD_RUM_ENABLED is true but stable "
                 "configuration provided no RUM snippet");
  }

  g_enabled_by_default = *parsed;
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
