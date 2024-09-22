#pragma once

#include "http_core.h"
#include "httpd.h"

const char* dd_enable_crash_tracker(cmd_parms* cmd, void* cfg, int value);

#define CRASH_TRACKER_MODULE_CMDS                                         \
  AP_INIT_FLAG("DatadogCrashTracker",                                     \
               reinterpret_cast<cmd_func>(dd_enable_crash_tracker), NULL, \
               RSRC_CONF | ACCESS_CONF,                                   \
               "Enable or disable Datadog Crash Tracker"),
