#include <datadog/tracer_config.h>
#include <http_core.h>

namespace datadog::tracing::conf {

// Initialize configuration for Tracing
//
// @param conf            Tracer configuration
// @param runtime_id      Worker runtime ID
// @param server          Server instance
// @param datadog_module  Datadog module
void init(TracerConfig& conf, RuntimeID& runtime_id, server_rec* server,
          module* datadog_module);

}  // namespace datadog::tracing::conf
