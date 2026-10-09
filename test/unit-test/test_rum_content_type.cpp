#include <catch2/catch.hpp>

#include "rum/content_type.h"

TEST_CASE("RUM accepts HTML media types", "[rum]") {
  const char* content_types[] = {"text/html",
                                 "TEXT/HTML",
                                 "TeXt/HtMl",
                                 "text/html; charset=utf-8",
                                 "TEXT/HTML; charset=UTF-8",
                                 " \ttext/html\t ",
                                 "text/html \t; charset=utf-8"};
  for (const char* content_type : content_types) {
    INFO(content_type);
    CHECK(datadog::rum::is_html_content_type(content_type));
  }
}

TEST_CASE("RUM rejects missing and non-HTML media types", "[rum]") {
  const char* content_types[] = {nullptr,
                                 "",
                                 " \t",
                                 "; charset=utf-8",
                                 "application/javascript",
                                 "text/javascript; charset=utf-8",
                                 "text/plain",
                                 "application/json",
                                 "text/css",
                                 "application/xhtml+xml",
                                 "text/htmlish",
                                 "application/x-text/html",
                                 "application/javascript; note=text/html",
                                 "text/html, application/javascript",
                                 "text /html",
                                 "text/html\r\n"};
  for (const char* content_type : content_types) {
    INFO((content_type ? content_type : "<unset>"));
    CHECK_FALSE(datadog::rum::is_html_content_type(content_type));
  }
}
