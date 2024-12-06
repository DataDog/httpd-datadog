#pragma once

#include <datadog/tracer_config.h>

#include <string>
#include <string_view>
#include <unordered_map>

#include "apr_poll.h"
#include "httpd.h"
#if defined(HTTPD_DD_RUM)
#include "injectbrowsersdk.h"
#endif

namespace datadog::conf {

struct Module final {
  tracing::TracerConfig tracing;
};

struct Directory final {
  bool tracing_enabled = true;
  bool delegate_sampling = false;
  bool trust_inbound_span = true;
  std::unordered_map<std::string, std::string> tags;

  // RUM
#if defined(HTTPD_DD_RUM)
  bool rum_enabled = false;
  Snippet* snippet = nullptr;
  std::unordered_map<std::string, std::string> rum_config;
#endif
};

void* init_dir_conf(apr_pool_t* pool, char*);

void* merge_dir_conf(apr_pool_t* pool, void* base, void* add);

}  // namespace datadog::conf
