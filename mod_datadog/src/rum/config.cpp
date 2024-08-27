#include "rum/config.h"

#include <optional>
#include <string>
#include <string_view>

#include "apr_file_io.h"
#include "apr_strings.h"
#include "common_conf.h"

using namespace datadog::conf;

const char* enable_rum_ddog(cmd_parms* /* cmd */, void* cfg, int value) {
  auto* dir_conf = static_cast<Directory*>(cfg);
  dir_conf->rum_enabled = (bool)value;
  return NULL;
}

const char* set_rum_setting(cmd_parms* /*cmd*/, void* cfg, const char* key,
                            const char* value) {
  auto* dir_conf = static_cast<Directory*>(cfg);

  dir_conf->rum_config.emplace(key, value);
  return NULL;
}
