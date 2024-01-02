#pragma once

#include <string>

namespace utils {

inline void to_lower(std::string& text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char ch) { return std::tolower(ch); });
}

}  // namespace utils
