// #include "utils.h"
#include <catch2/catch.hpp>

std::unordered_map<std::string, std::string>
parse_http_header_tags(std::string_view in) {
  std::unordered_map<std::string, std::string> res;

  const std::size_t end = in.size();

  for (std::size_t beg = 0; beg < end;) {
    beg = in.find_first_not_of(' ', beg);
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

TEST_CASE("Parse HTTP Header Tags", "[http_header_tags]") {
  CHECK(parse_http_header_tags(" user-agent ") ==
        std::unordered_map<std::string, std::string>{{"user-agent", ""}});
}
