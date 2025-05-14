#include "telemetry.h"

using namespace datadog::telemetry;

namespace datadog::rum::telemetry {

std::shared_ptr<Counter> injection_skipped(new Counter{"injection.skipped",
                                                       "rum", true});
std::shared_ptr<Counter> injection_succeed(new Counter{"injection.succeed",
                                                       "rum", true});
std::shared_ptr<Counter> injection_failed(new Counter{"injection.failed", "rum",
                                                      true});
std::shared_ptr<Counter> content_security_policy(new Counter{
    "injection.content_security_policy", "rum", true});

}  // namespace datadog::rum::telemetry
