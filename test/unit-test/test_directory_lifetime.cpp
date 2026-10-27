// AddressSanitizer reports leaked directory configs when the binary exits.
#include <apr_general.h>

#include <catch2/catch.hpp>
#include <string>

#include "common_conf.h"

using datadog::conf::Directory;

#if defined(HTTPD_DD_RUM)
// Called by datadog_rum_settings_section(). httpd itself is not linked.
extern "C" const char* ap_walk_config(ap_directive_t*, cmd_parms*,
                                      ap_conf_vector_t*) {
  return nullptr;
}
#endif

namespace {

Directory* make_directory(apr_pool_t* pool) {
  return static_cast<Directory*>(datadog::conf::init_dir_conf(pool, nullptr));
}

const Directory* merge(apr_pool_t* pool, Directory* parent, Directory* child) {
  return static_cast<const Directory*>(
      datadog::conf::merge_dir_conf(pool, parent, child));
}

#if defined(HTTPD_DD_RUM)
const char* configure_rum(apr_pool_t* pool, Directory* directory,
                          const char* section_argument) {
  command_rec command = {};
  command.name = "<DatadogRumSettings";
  ap_directive_t directive = {};
  cmd_parms parameters = {};
  parameters.pool = pool;
  parameters.cmd = &command;
  parameters.directive = &directive;
  directory->rum.config = {{"applicationId", "test-app"},
                           {"clientToken", "test-token"}};
  return datadog_rum_settings_section(&parameters, directory,
                                      section_argument);
}
#endif

}  // namespace

TEST_CASE("Merged directory configs release their tags", "[directory]") {
  apr_initialize();
  apr_pool_t* pool = nullptr;
  apr_pool_create(&pool, nullptr);
  Directory* parent = make_directory(pool);
  Directory* child = make_directory(pool);
  parent->tags.emplace("parent_tag", std::string(4096, 'p'));
  child->tags.emplace("child_tag", std::string(64, 'c'));
  for (int request = 0; request < 100; ++request) {
    apr_pool_t* request_pool = nullptr;
    apr_pool_create(&request_pool, pool);
    const Directory* merged = merge(request_pool, parent, child);
    CHECK(merged->tags.at("parent_tag") == parent->tags.at("parent_tag"));
    CHECK(merged->tags.at("child_tag") == child->tags.at("child_tag"));
    apr_pool_destroy(request_pool);
  }
  apr_pool_destroy(pool);
  apr_terminate();
}

#if defined(HTTPD_DD_RUM)
TEST_CASE("Merged directory configs share the parent RUM snippet",
          "[directory][rum]") {
  apr_initialize();
  apr_pool_t* pool = nullptr;
  apr_pool_create(&pool, nullptr);
  Directory* parent = make_directory(pool);
  Directory* child = make_directory(pool);
  REQUIRE(configure_rum(pool, parent, "\"v6\">") == nullptr);
  // A second section replaces the first snippet.
  REQUIRE(configure_rum(pool, parent, "\"v6\">") == nullptr);
  // An unsupported version fails, and the child keeps no snippet.
  REQUIRE(configure_rum(pool, child, "\"v999\">") != nullptr);
  REQUIRE(child->rum.snippet == nullptr);
  for (int request = 0; request < 100; ++request) {
    apr_pool_t* request_pool = nullptr;
    apr_pool_create(&request_pool, pool);
    const Directory* merged = merge(request_pool, parent, child);
    CHECK(merged->rum.snippet == parent->rum.snippet);
    apr_pool_destroy(request_pool);
    CHECK(parent->rum.snippet->error_code == 0);
  }
  apr_pool_destroy(pool);
  apr_terminate();
}
#endif
