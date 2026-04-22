#pragma once

#include <datadog/tracer_config.h>

#include <optional>
#include <string>
#include <unordered_map>

#include "apr_poll.h"

#if defined(HTTPD_DD_RUM)
#include "rum/config.h"
#endif

namespace datadog::conf {

struct Module final {
  tracing::TracerConfig tracing;
};

struct Directory final {
  // `std::nullopt` means "inherit from the enclosing scope"; any concrete
  // value (true/false) was set explicitly via a directive and wins over the
  // parent during merge. The effective default at read sites is `true`.
  std::optional<bool> tracing_enabled;
  std::optional<bool> trust_inbound_span;
  std::unordered_map<std::string, std::string> tags;

  // RUM
#if defined(HTTPD_DD_RUM)
  rum::conf::Directory rum;
#endif
};

void* init_dir_conf(apr_pool_t* pool, char*);

void* merge_dir_conf(apr_pool_t* pool, void* base, void* add);

}  // namespace datadog::conf
