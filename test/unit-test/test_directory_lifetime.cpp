#include "common_conf.h"

#include <apr_general.h>

#include <cassert>
#include <string>

#if defined(HTTPD_DD_RUM)
extern "C" const char* ap_walk_config(ap_directive_t*, cmd_parms*,
                                     ap_conf_vector_t*) {
  return nullptr;
}

static void configure_snippet(apr_pool_t* pool,
                              datadog::conf::Directory* directory,
                              const char* version = "\"v6\">") {
  command_rec command = {};
  command.name = "<DatadogRumSettings";
  ap_directive_t directive = {};
  cmd_parms parameters = {};
  parameters.pool = pool;
  parameters.cmd = &command;
  parameters.directive = &directive;
  directory->rum.config = {{"applicationId", "test-app"},
                           {"clientToken", "test-token"}};
  const char* error =
      datadog_rum_settings_section(&parameters, directory, version);
  assert((error != nullptr) == (std::string(version) == "\"v999\">"));
}
#endif

int main() {
  apr_initialize();
  apr_pool_t* configuration_pool = nullptr;
  apr_pool_create(&configuration_pool, nullptr);
  auto* parent = static_cast<datadog::conf::Directory*>(
      datadog::conf::init_dir_conf(configuration_pool, nullptr));
  auto* child = static_cast<datadog::conf::Directory*>(
      datadog::conf::init_dir_conf(configuration_pool, nullptr));
  parent->tags.emplace("large_tag", std::string(4096, 'x'));
  child->tags.emplace("child_tag", "child");
#if defined(HTTPD_DD_RUM)
  configure_snippet(configuration_pool, parent);
  configure_snippet(configuration_pool, parent);
  configure_snippet(configuration_pool, child, "\"v999\">");
#endif
  for (int index = 0; index < 100; ++index) {
    apr_pool_t* request_pool = nullptr;
    apr_pool_create(&request_pool, configuration_pool);
    auto* merged = static_cast<datadog::conf::Directory*>(
        datadog::conf::merge_dir_conf(request_pool, parent, child));
    assert(merged->tags.at("large_tag") == parent->tags.at("large_tag"));
    assert(merged->tags.at("child_tag") == "child");
#if defined(HTTPD_DD_RUM)
    assert(merged->rum.snippet == parent->rum.snippet);
    assert(merged->rum.snippet->error_code == 0);
#endif
    apr_pool_destroy(request_pool);
#if defined(HTTPD_DD_RUM)
    assert(parent->rum.snippet->error_code == 0);
#endif
  }
  apr_pool_destroy(configuration_pool);
  apr_terminate();
}
