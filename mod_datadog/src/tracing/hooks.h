#include <datadog/tracer.h>
#include <http_core.h>

namespace datadog::tracing {

int on_fixups(request_rec* r, Tracer& g_tracer, module* datadog_module);
int on_log_transaction(request_rec* r, module* datadog_module);

}  // namespace datadog::tracing
