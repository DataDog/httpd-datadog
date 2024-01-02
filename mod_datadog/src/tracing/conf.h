#include <datadog/tracer_config.h>
#include <http_core.h>

namespace datadog::tracing::conf {

// Initialize configuration for Tracing
//
// @param conf Tracer configuration
// @param TBD
void init(TracerConfig&, RuntimeID&, server_rec*, module*);

}  // namespace datadog::tracing::conf
