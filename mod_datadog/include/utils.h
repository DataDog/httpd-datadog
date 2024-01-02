#pragma once

#include <datadog/span.h>
#include <string_view>

namespace utils {

// NOTE(@dmehala): Temporarly implement `DD_TRACE_HEADER_TAGS` until
// it is supported by dd-trace-cpp.
class HeaderTags {
  std::unordered_map<std::string, std::string> header_to_tag_;

public:
  HeaderTags(std::string_view in);

  void process(datadog::tracing::Span &span,
               std::function<std::optional<std::string_view>(std::string_view)>
                   header_lookup);

private:
  std::unordered_map<std::string, std::string>
  parse_header_tags(std::string_view in);
};

inline std::unique_ptr<HeaderTags> make_header_tags() {
  if (const char *value = std::getenv("DD_TRACE_HEADER_TAGS"); value) {
    return std::make_unique<utils::HeaderTags>(value);
  }

  return nullptr;
}

} // namespace utils
