#pragma once

#include <string_view>

// Store httpd-datadog version following the Semantic Versioning (semver)
// format. Version format: <version>+<build-id>
//
// The `build-id` is generated as follows:
//   1. For Debug builds, the build-id starts with "dev" followed by the current
//   date (YYYYMMDD).
//   2. If Git is available, the build-id will include the latest commit hash.
//      Otherwise, it will fall back to using the machine's hostname.
extern const std::string_view mod_datadog_version;
extern const std::string_view mod_datadog_version_string;

#if defined(HTTPD_DD_RUM)
extern const char datadog_semver_rum_injector[];
extern const char datadog_version_rum_injector[];
#endif
