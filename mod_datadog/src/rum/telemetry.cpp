#include "telemetry.h"

using namespace datadog::telemetry;

namespace datadog::rum::telemetry {

const Counter injection_skipped{"injection.skipped", "rum", true};
const Counter injection_succeed{"injection.succeed", "rum", true};
const Counter injection_failed{"injection.failed", "rum", true};
const Counter content_security_policy{"injection.content_security_policy",
                                      "rum", true};

}  // namespace datadog::rum::telemetry
