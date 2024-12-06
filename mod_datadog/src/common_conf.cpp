#include "common_conf.h"

namespace datadog::conf {

void* init_dir_conf(apr_pool_t* pool, char*) {
  void* buffer = apr_pcalloc(pool, sizeof(Directory));
  new (buffer) Directory;
  return buffer;
}

void* merge_dir_conf(apr_pool_t* pool, void* base, void* add) {
  auto parent = static_cast<Directory*>(base);
  auto child = static_cast<Directory*>(add);

  void* final_ptr = init_dir_conf(pool, nullptr);
  auto conf = static_cast<Directory*>(final_ptr);

  conf->tracing_enabled = child->tracing_enabled || parent->tracing_enabled;

  conf->delegate_sampling =
      child->delegate_sampling || parent->delegate_sampling;

  conf->trust_inbound_span =
      child->trust_inbound_span || parent->trust_inbound_span;

  conf->tags = child->tags;
  auto tmp = parent->tags;
  conf->tags.merge(tmp);

  rum::conf::merge_directory_configuration(conf->rum, parent->rum, child->rum);

  return final_ptr;
}
}  // namespace datadog::conf
