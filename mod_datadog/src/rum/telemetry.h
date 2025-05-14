#include <datadog/telemetry/metrics.h>
#include <datadog/telemetry/telemetry.h>
#include <fmt/core.h>

#include <string>
#include <utility>
#include <vector>

#include "version.h"

namespace datadog::rum::telemetry {

template <typename... T>
auto build_tags(T&&... specific_tags) {
  std::vector<std::string> tags = {std::forward<T>(specific_tags)...};
  tags.emplace_back("integration_name:httpd");
  tags.emplace_back("injector_version:0.1.0");
  tags.emplace_back(fmt::format("integration_version:{}", mod_datadog_version));

  return tags;
}

extern std::shared_ptr<datadog::telemetry::Counter> injection_skipped;
extern std::shared_ptr<datadog::telemetry::Counter> injection_succeed;
extern std::shared_ptr<datadog::telemetry::Counter> injection_failed;
extern std::shared_ptr<datadog::telemetry::Counter> content_security_policy;

}  // namespace datadog::rum::telemetry
