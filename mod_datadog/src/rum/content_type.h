#pragma once

#include <string_view>

#include "string_utils.h"

namespace datadog::rum {

inline std::string_view media_type_of(std::string_view content_type);

inline bool is_html_content_type(const char* content_type) {
  if (!content_type) {
    return false;
  }

  std::string media_type{media_type_of(content_type)};
  datadog::common::utils::to_lower(media_type);
  return media_type == "text/html";
}

inline std::string_view media_type_of(std::string_view content_type) {
  const std::string_view media_type =
      content_type.substr(0, content_type.find(';'));
  const std::size_t start = media_type.find_first_not_of(" \t");
  if (start == std::string_view::npos) {
    return {};
  }
  const std::size_t end = media_type.find_last_not_of(" \t");
  return media_type.substr(start, end - start + 1);
}

}  // namespace datadog::rum
