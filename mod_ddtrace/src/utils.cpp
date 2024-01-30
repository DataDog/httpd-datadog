#include "utils.h"

namespace utils {

HeaderTags::HeaderTags(std::string_view in)
    : header_to_tag_(parse_header_tags(in)) {}

void HeaderTags::process(
    datadog::tracing::Span &span,
    std::function<std::optional<std::string_view>(std::string_view)>
        header_lookup) {
  for (const auto &[header, tag] : header_to_tag_) {
    if (const auto header_value = header_lookup(header)) {
      span.set_tag(tag, *header_value);
    }
  }
}

// TODO: Follow the RFC recommendation
// <https://datadoghq.atlassian.net/wiki/spaces/APMINT/pages/2302444638/DD+TRACE+HEADER+TAGS>
std::unordered_map<std::string, std::string>
HeaderTags::parse_header_tags(std::string_view in) {
  std::unordered_map<std::string, std::string> res;

  const std::size_t end = in.size();

  for (std::size_t beg = 0; beg < end;) {
    std::size_t comma_idx = in.find(',', beg);
    if (comma_idx == std::string_view::npos) {
      comma_idx = end;
    }

    auto kv = in.substr(beg, comma_idx - beg);
    beg = comma_idx + 1;

    std::size_t colon_idx = kv.find(':');
    if (colon_idx == std::string_view::npos) {
      continue;
    }

    auto http_header = kv.substr(0, colon_idx);
    auto tag = kv.substr(colon_idx + 1);

    res[std::string(http_header)] = tag;
  }

  return res;
}

} // namespace utils
