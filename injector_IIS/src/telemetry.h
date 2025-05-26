/*
 * Unless explicitly stated otherwise all files in this repository are licensed
 * under the Apache 2.0 License. This product includes software developed at
 * Datadog (https://www.datadoghq.com/).
 *
 * Copyright 2024-Present Datadog, Inc.
 */

#pragma once

#include "version.h"
#include <datadog/telemetry/metrics.h>
#include <format>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace datadog::rum::telemetry {

template <typename... T> auto build_tags(T &&...specific_tags) {
  std::vector<std::string> tags = {std::forward<T>(specific_tags)...};
  tags.emplace_back("integration_name:iis");
  tags.emplace_back(std::format(
      "injector_version:{}", std::string_view{datadog_rum_injector_version}));
  tags.emplace_back(
      std::format("integration_version:{}", SHORT_VERSION_STRING));

  return tags;
}

const extern datadog::telemetry::Counter injection_skipped;
const extern datadog::telemetry::Counter injection_succeed;
const extern datadog::telemetry::Counter injection_failed;
const extern datadog::telemetry::Counter content_security_policy;

} // namespace datadog::rum::telemetry
