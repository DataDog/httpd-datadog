#include "crash-tracker/conf.h"

#include <mpm_common.h>

/*#include "common_conf.h"*/

const char* dd_enable_crash_tracker(cmd_parms* cmd, void* cfg, int value) {
  /*auto* module_conf = static_cast<datadog::conf::Module*>(*/
  /*    ap_get_module_config(cmd->server->module_config, &datadog_module));*/

  if (value) {
    ap_mpm_set_exception_hook(cmd, cfg, "on");
  }
  /*module_conf->tracing.environment = arg;*/
  return NULL;
}
