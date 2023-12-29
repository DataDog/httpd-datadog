#pragma once

#include "apr_poll.h"
#include "httpd.h"

#include <string>
#include <string_view>

struct DirectoryConf final {
  bool enabled = true;
  bool trust_inbound_span = true;
  std::unordered_map<std::string, std::string> tags;
  std::string_view resource_name;
  // std::string_view operation_name;
  std::string_view propagation_styles;
};

inline void *init_dir_conf(apr_pool_t *pool, char *) {
  void *buffer = apr_pcalloc(pool, sizeof(DirectoryConf));
  new (buffer) DirectoryConf;
  return buffer;
}
