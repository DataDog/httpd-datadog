#pragma once

#include "http_core.h"
#include "httpd.h"

inline const char* rum_filter_name = "mod_rum_inject";

const char* enable_rum_ddog(cmd_parms* cmd, void* cfg, int value);
const char* set_rum_setting(cmd_parms* cmd, void* cfg, const char* value,
                            const char* value2);

// clang-format off
#define RUM_MODULE_CMDS \
  AP_INIT_FLAG("DatadogRum", reinterpret_cast<cmd_func>(enable_rum_ddog), NULL, RSRC_CONF | ACCESS_CONF, "Enable or disable Datadog RUM module"), \
  AP_INIT_TAKE2("DatadogRumSetting", reinterpret_cast<cmd_func>(set_rum_setting), NULL, RSRC_CONF | ACCESS_CONF, "Set RUM JSON configuration"),
// clang-format on
