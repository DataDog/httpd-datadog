#pragma once

#include <fmt/core.h>
#include <httpd.h>

#include <string>

namespace datadog::common::utils {

inline void to_lower(std::string& text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char ch) { return std::tolower(ch); });
}

inline std::string make_httpd_version() {
  ap_version_t httpd_version;
  ap_get_server_revision(&httpd_version);

  if (httpd_version.add_string && strlen(httpd_version.add_string) != 0) {
    return fmt::format("{}.{}.{}-{}", httpd_version.major, httpd_version.minor,
                       httpd_version.patch, httpd_version.add_string);
  }

  return fmt::format("{}.{}.{}", httpd_version.major, httpd_version.minor,
                     httpd_version.patch);
}

inline bool contains(std::string_view text, std::string_view pattern) {
  return text.find(pattern) != text.npos;
}

}  // namespace datadog::common::utils
