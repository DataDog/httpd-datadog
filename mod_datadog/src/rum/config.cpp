#include "rum/config.h"

#include <fmt/format.h>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <string>
#include <string_view>

#include "apr_strings.h"
#include "common_conf.h"
#include "mod_datadog.h"
#include "utils.h"

using namespace datadog::conf;

namespace {
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
  dir_conf->rum.enabled = (bool)value;
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

  Snippet* snippet = snippet_create_from_json(json_config.c_str());
  if (snippet->error_code != 0) {
    return apr_psprintf(cmd->pool, "Failed to initialize RUM SDK injection: %s",
                        snippet->error_message);
  }

  dir_conf.rum.snippet = snippet;

  return NULL;
}

namespace datadog::rum::conf {

void merge_directory_configuration(Directory& out, const Directory& parent,
                                   const Directory& child) {
  out.enabled = child.enabled || parent.enabled;
  out.snippet = child.snippet ? child.snippet : parent.snippet;
  return;
}
}  // namespace datadog::rum::conf
