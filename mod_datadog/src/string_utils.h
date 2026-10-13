#pragma once

#include <algorithm>
#include <cctype>
#include <string>

namespace datadog::common::utils {

inline void to_lower(std::string& text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char ch) { return std::tolower(ch); });
}

}  // namespace datadog::common::utils
