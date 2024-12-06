#include "rum/config.h"

#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <optional>
#include <string>
#include <string_view>

#include "apr_file_io.h"
#include "apr_strings.h"
#include "common_conf.h"
#include "mod_datadog.h"

using namespace datadog::conf;

namespace {
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
    if (key == "majorVersion") {
      continue;
    } else if (key == "sessionSampleRate" || key == "sessionReplaySampleRate") {
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(std::stod(value)).Move(), allocator);
    } else if (key == "trackResources" || key == "trackLongTasks" ||
               key == "trackUserInteractions") {
      auto b = (value == "true" ? true : false);
      rum.AddMember(rapidjson::Value(key.c_str(), allocator).Move(),
                    rapidjson::Value(b).Move(), allocator);
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
  dir_conf->rum_enabled = (bool)value;
  return NULL;
}

const char* set_rum_option(cmd_parms* cmd, void* cfg, const char* key,
                           const char* value) {
  if (cmd->directive->parent == nullptr ||
      std::string_view(cmd->directive->parent->directive) !=
          "<DatadogRumSettings") {
    return apr_pstrcat(cmd->pool, cmd->cmd->name,
                       " cannot occur outside <DatadogRumSettings> section",
                       NULL);
  }

  auto* dir_conf = static_cast<Directory*>(cfg);

  dir_conf->rum_config.emplace(key, value);
  return NULL;
}

const char* datadog_rum_settings_section(cmd_parms* cmd, void* cfg,
                                         const char* arg) {
  const char* endp = ap_strrchr_c(arg, '>');
  if (endp == nullptr) {
    return apr_pstrcat(cmd->pool, cmd->cmd->name,
                       "> directive missing closing '>'", nullptr);
  }

  const char* err =
      ap_walk_config(cmd->directive->first_child, cmd, cmd->context);
  if (err != nullptr) {
    return err;
  }

  auto& dir_conf = *static_cast<Directory*>(cfg);

  const auto json_config = make_rum_json_config("v5", dir_conf.rum_config);
  if (json_config.empty()) {
    return "failed to generate the RUM SDK script";
  }

  Snippet* snippet = snippet_create_from_json(json_config.c_str());
  if (snippet->error_code != 0) {
    return apr_psprintf(cmd->pool, "Failed to initialize RUM SDK injection: %s",
                        snippet->error_message);
  }

  // TODO(@dmehala): cleanup
  dir_conf.snippet = snippet;
  /*apr_pool_cleanup_register(*/
  /*    cmd->pool, (void*)ctx->snippet,*/
  /*    [](void* p) -> apr_status_t {*/
  /*      snippet_cleanup((Snippet*)p);*/
  /*      return 0;*/
  /*    },*/
  /*    apr_pool_cleanup_null);*/

  return NULL;
}
