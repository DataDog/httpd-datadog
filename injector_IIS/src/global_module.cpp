// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache 2.0 License. This product includes software developed at
// Datadog (https://www.datadoghq.com/).
//
// Copyright 2024-Present Datadog, Inc.

#include "global_module.h"
#include "defer.h"
#include "injectbrowsersdk.h"
#include "module_context.h"
#include "telemetry.h"
#include <cassert>
#include <datadog/tracer_config.h>
#include <format>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <string>

namespace datadog::rum {
namespace {

std::string wstring_to_utf8(const std::wstring &wstr) {
  if (wstr.empty())
    return std::string();
  const int size_needed = WideCharToMultiByte(
      CP_UTF8, 0, &wstr[0], (int)wstr.size(), nullptr, 0, nullptr, nullptr);
  std::string strTo(size_needed, 0);
  WideCharToMultiByte(CP_UTF8, 0, &wstr[0], (int)wstr.size(), &strTo[0],
                      size_needed, nullptr, nullptr);
  return strTo;
}

Snippet *
make_snippet(const int version,
             const std::unordered_map<std::string, std::string> &opts) {
  rapidjson::Document doc;
  doc.SetObject();

  rapidjson::Document::AllocatorType &allocator = doc.GetAllocator();
  doc.AddMember("majorVersion", version, allocator);

  rapidjson::Value rum(rapidjson::kObjectType);
  for (const auto &[key, value] : opts) {
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

  return snippet_create_from_json(buffer.GetString());
}

IAppHostProperty *get_property(IAppHostElement *xmlElement,
                               std::wstring_view name) {
  assert(xmlElement);
  IAppHostProperty *property = nullptr;
  if (xmlElement->GetPropertyByName((BSTR)name.data(), &property) != S_OK) {
    return nullptr;
  }

  return property;
}

VARIANT get_property_value(IAppHostProperty &property) {
  VARIANT v;
  property.get_Value(&v);
  return v;
}

std::optional<RumConfig> read_conf(IHttpServer &server, PCWSTR cfg_path) {
  auto admin_manager = server.GetAdminManager();
  IAppHostElement *cfg_root_elem;
  auto res = admin_manager->GetAdminSection(
      (BSTR)L"system.webServer/datadogRum", const_cast<BSTR>(cfg_path),
      &cfg_root_elem);
  if (res != S_OK) {
    return std::nullopt;
  }

  const auto defer_root = defer([&] { cfg_root_elem->Release(); });

  IAppHostProperty *enabled_prop = get_property(cfg_root_elem, L"enabled");
  if (enabled_prop == nullptr) {
    // missing enabled attribute -> invalid format -> disabled
    return std::nullopt;
  }

  const auto defer_enabled_prop = defer([&] { enabled_prop->Release(); });

  const auto is_enabled = get_property_value(*enabled_prop).boolVal;
  if (!is_enabled) {
    return std::nullopt;
  }

  int cfg_version = 6;
  auto version_prop = get_property(cfg_root_elem, L"version");
  if (version_prop != nullptr) {
    const auto defer_version_prop = defer([&] { version_prop->Release(); });
    cfg_version = get_property_value(*version_prop).iVal;
  }

  // Iterate on the SDK configuration
  std::unordered_map<std::string, std::string> rum_sdk_opts;

  IAppHostElementCollection *col = nullptr;
  if (cfg_root_elem->get_Collection(&col) == S_OK) {
    const auto defer_col = defer([&] { col->Release(); });

    DWORD n_elem = 0;
    col->get_Count(&n_elem);

    VARIANT item_idx;
    item_idx.vt = VT_I2;

    for (DWORD i = 0; i < n_elem; ++i) {
      item_idx.iVal = static_cast<SHORT>(i);

      IAppHostElement *option_element = nullptr;
      col->get_Item(item_idx, &option_element);
      if (option_element == nullptr) {
        continue;
      }

      const auto option_element_guard =
          defer([&] { option_element->Release(); });

      auto name_property = get_property(option_element, L"name");
      if (name_property == nullptr) {
        // TODO: log property `name` do not exist
        continue;
      }
      const auto defer_name_property = defer([&] { name_property->Release(); });
      std::string opt_name = wstring_to_utf8(
          std::wstring(get_property_value(*name_property).bstrVal));

      auto value_property = get_property(option_element, L"value");
      if (value_property == nullptr) {
        continue;
      }
      const auto defer_value_property =
          defer([&] { value_property->Release(); });
      std::string opt_value = wstring_to_utf8(
          std::wstring(get_property_value(*value_property).bstrVal));

      rum_sdk_opts.emplace(std::move(opt_name), std::move(opt_value));
    }
  }

  return RumConfig{cfg_version, std::move(rum_sdk_opts)};
}

void update_module_context(ModuleContext &ctx, IHttpServer &server,
                           PCWSTR config_path, std::shared_ptr<Logger> logger) {

  auto config_options_opt = read_conf(server, config_path);
  if (!config_options_opt.has_value()) {
    logger->error("Failed to load RUM configuration");
    return;
  }
  const RumConfig &loaded_config = config_options_opt.value();
  Snippet *snippet =
      make_snippet(loaded_config.version, loaded_config.sdk_options);

  if (snippet == nullptr) {
    logger->error("Failed to create RUM snippet");
    return;
  } else if (snippet->error_code != 0) {
    logger->error(std::format("Failed to create RUM snippet: {}",
                              snippet->error_message));
    return;
  }

  logger->info("Configuration validated");
  ctx.js_snippet = snippet;

  if (auto appIdIt = loaded_config.sdk_options.find("applicationId");
      appIdIt != loaded_config.sdk_options.end()) {
    ctx.application_id_tag = std::format("application_id:{}", appIdIt->second);
  }

  auto rcUsed = loaded_config.sdk_options.count("remoteConfigurationId") > 0;
  ctx.remote_config_tag = std::format("remote_config_used:{}", rcUsed);
}
} // namespace

GlobalModule::GlobalModule(IHttpServer *server, DWORD server_version,
                           std::shared_ptr<Logger> logger)
    : server_(server), logger_(std::move(logger)) {
  assert(server_ != nullptr);

  // TODO(@dmehala): Add `rum` product in `app-started` event.
  datadog::telemetry::Configuration cfg;
  cfg.enabled = true;
  cfg.integration_name = "iis";
  cfg.integration_version = std::to_string(server_version);

  auto maybe_telemetry_cfg = datadog::telemetry::finalize_config(cfg);
  if (auto error = maybe_telemetry_cfg.if_error()) {
    logger_->error(std::format("Failed to configure the telemetry module: {}",
                               error->message));
  } else {

    const datadog::tracing::Clock &clock = datadog::tracing::default_clock;
    datadog::tracing::DatadogAgentConfig agent_cfg_for_telemetry;
    auto finalized_agent_cfg_result = datadog::tracing::finalize_config(
        agent_cfg_for_telemetry, logger_, clock);
    if (auto *error = finalized_agent_cfg_result.if_error()) {
      logger_->log_error(
          error->with_prefix("Failed to finalize agent settings for "
                             "telemetry, no telemetry will be sent."));

      return;
    }
    datadog::tracing::FinalizedDatadogAgentConfig dac =
        *finalized_agent_cfg_result;

    if (!dac.http_client) {
      logger_->error(
          "HTTPClient for telemetry is null, no telemetry will be sent");
      return;
    }

    datadog::telemetry::init(*maybe_telemetry_cfg, logger_, dac.http_client,
                             dac.event_scheduler, dac.url, clock);
  }
}

void GlobalModule::Terminate() { delete this; }

GLOBAL_NOTIFICATION_STATUS
GlobalModule::OnGlobalApplicationStart(
    IHttpApplicationStartProvider *provider) {
  assert(server_ != nullptr);

  auto ctx = new ModuleContext;
  ctx->logger = logger_.get();

  auto app = provider->GetApplication();
  assert(app);

  auto config_path = app->GetAppConfigPath();
  logger_->info(std::format("Parsing configuration \"{}\" for app (id: {})",
                            wstring_to_utf8(config_path),
                            wstring_to_utf8(app->GetApplicationId())));

  update_module_context(*ctx, *server_, config_path, logger_);
  app->GetModuleContextContainer()->SetModuleContext(ctx, g_module_id);

  // NOTE(@dmehala): Keep a reference on the module context for
  // `OnGlobalConfigurationChange` event.
  configurations_.emplace(config_path, ctx);

  return GL_NOTIFICATION_CONTINUE;
}

GLOBAL_NOTIFICATION_STATUS
GlobalModule::OnGlobalApplicationStop(IHttpApplicationStopProvider *provider) {
  auto cfg_path = provider->GetApplication()->GetApplicationId();
  if (cfg_path == nullptr) {
    return GL_NOTIFICATION_CONTINUE;
  }

  configurations_.erase(cfg_path);
  return GL_NOTIFICATION_CONTINUE;
}

GLOBAL_NOTIFICATION_STATUS GlobalModule::OnGlobalConfigurationChange(
    IGlobalConfigurationChangeProvider *provider) {
  assert(provider != nullptr);
  assert(server_ != nullptr);

  auto cfg_path = provider->GetChangePath();
  if (cfg_path == nullptr) {
    assert(true);
    return GL_NOTIFICATION_CONTINUE;
  }

  logger_->info(std::format("Dispatching configuration update (\"{}\")",
                            wstring_to_utf8(cfg_path)));

  // NOTE(@dmehala): There's a mismatch between the config path given in
  // `OnGlobalApplicationStart` and the one here. This path is the common parent
  // config, we need to ensure the update is sent to all applications that
  // inherit from it.
  for (const auto &[path, ctx] : configurations_) {
    if (ctx == nullptr) {
      // NOTE(@dmehala): should not happend because configuration entries are
      // removed when an application is stopped. This should be considered as a
      // bug.
      // TODO(@dmehala): Report a telemetry log.
      assert(true);
      continue;
    }

    // Question(@dmehala): should the default behaviour to keep the old setting
    // if there's an issue with the configuration?
    if (std::wstring_view(path).starts_with(cfg_path)) {
      update_module_context(*ctx, *server_, provider->GetChangePath(), logger_);
    }
  }

  return GL_NOTIFICATION_CONTINUE;
}
} // namespace datadog::rum
