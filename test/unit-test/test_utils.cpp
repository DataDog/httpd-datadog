#include "utils.h"

#include <catch2/catch.hpp>
#include <string>

using namespace datadog::common::utils;

TEST_CASE("to_lower", "[utils]") {
  SECTION("lowercases in place") {
    std::string text = "X-Datadog-Trace-Id";
    to_lower(text);
    CHECK(text == "x-datadog-trace-id");
  }

  SECTION("leaves already-lowercase text alone") {
    std::string text = "user-agent";
    to_lower(text);
    CHECK(text == "user-agent");
  }

  SECTION("leaves non-alphabetic characters alone") {
    std::string text = "A1_-.:/B";
    to_lower(text);
    CHECK(text == "a1_-.:/b");
  }

  SECTION("handles the empty string") {
    std::string text;
    to_lower(text);
    CHECK(text.empty());
  }
}

TEST_CASE("contains", "[utils]") {
  CHECK(contains("text/html; charset=utf-8", "text/html"));
  CHECK(contains("text/html", "text/html"));

  SECTION("matches at either end") {
    CHECK(contains("abcdef", "abc"));
    CHECK(contains("abcdef", "def"));
  }

  SECTION("reports absent patterns") {
    CHECK_FALSE(contains("application/json", "text/html"));
    CHECK_FALSE(contains("", "text/html"));
  }

  SECTION("is case sensitive") {
    CHECK_FALSE(contains("TEXT/HTML", "text/html"));
  }

  SECTION("every string contains the empty pattern") {
    CHECK(contains("anything", ""));
    CHECK(contains("", ""));
  }
}
