#include <datadog/telemetry/metrics.h>
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
  tags.emplace_back(fmt::format("injector_version:{}",
                                std::string_view{datadog_semver_rum_injector}));
  tags.emplace_back(fmt::format("integration_version:{}", mod_datadog_version));

  return tags;
}

const extern datadog::telemetry::Counter injection_skipped;
const extern datadog::telemetry::Counter injection_succeed;
const extern datadog::telemetry::Counter injection_failed;
const extern datadog::telemetry::Counter content_security_policy;

}  // namespace datadog::rum::telemetry
