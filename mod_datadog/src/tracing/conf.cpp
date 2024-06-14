#include "conf.h"

#include <memory>
#include <string>

#include "../utils.h"
#include "logger.h"

namespace datadog::tracing::conf {

void init(TracerConfig& conf, RuntimeID& runtime_id, server_rec* s,
          module* datadog_module) {
  conf.service_type = "server";
  conf.logger = std::make_shared<HttpdLogger>(s, datadog_module->module_index);
  conf.runtime_id = runtime_id;
  conf.integration_name = "httpd";
  conf.integration_version = common::utils::make_httpd_version();
}

}  // namespace datadog::tracing::conf
