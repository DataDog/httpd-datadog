#pragma once

#include <string_view>

namespace datadog::rum {

inline bool is_html_content_type(const char* content_type) {
  if (!content_type) {
    return false;
  }

  std::string_view media_type{content_type};
  media_type = media_type.substr(0, media_type.find(';'));
  const std::size_t start = media_type.find_first_not_of(" \t");
  if (start == std::string_view::npos) {
    return false;
  }
  const std::size_t end = media_type.find_last_not_of(" \t");
  media_type = media_type.substr(start, end - start + 1);

  constexpr std::string_view html_type = "text/html";
  if (media_type.size() != html_type.size()) {
    return false;
  }
  for (std::size_t index = 0; index < media_type.size(); ++index) {
    const char character = media_type[index];
    const char lower = character >= 'A' && character <= 'Z'
                           ? character + ('a' - 'A')
                           : character;
    if (lower != html_type[index]) {
      return false;
    }
  }
  return true;
}

}  // namespace datadog::rum
