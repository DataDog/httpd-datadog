#include "conf.h"

#include <string>

#include "logger.h"

#define DD_MOD_VERSION "0.1.0"

namespace datadog::tracing::conf {

void init(TracerConfig& conf, RuntimeID& runtime_id, server_rec* s,
          module* datadog_module) {
  conf.service_type = "server";
  conf.logger = std::make_shared<HttpdLogger>(s, datadog_module->module_index);
  conf.runtime_id = runtime_id;
  conf.integration_name = "httpd";
  conf.integration_version = DD_MOD_VERSION;
}

}  // namespace datadog::tracing::conf
