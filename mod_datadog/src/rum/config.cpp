#include "rum/config.h"

#include <optional>
#include <string>
#include <string_view>

#include "apr_file_io.h"
#include "apr_strings.h"
#include "common_conf.h"

namespace {

std::optional<std::string> read_file(const char* const filepath,
                                     apr_pool_t* pool) {
  apr_file_t* fd;
  apr_fileperms_t perms;
  auto status = apr_file_open(&fd, filepath, APR_FOPEN_READ, perms, pool);
  if (status != APR_SUCCESS) {
    return std::nullopt;
  }

  apr_pool_cleanup_register(
      pool, (void*)fd, [](void* p) { return apr_file_close((apr_file_t*)p); },
      apr_pool_cleanup_null);

  char buffer[512];
  apr_size_t sz_read;
  std::string file_content;

  while (apr_file_eof(fd) != APR_EOF) {
    apr_file_read_full(fd, buffer, 512, &sz_read);
    file_content.append(buffer, 0, sz_read);
  }

  return file_content;
}

}  // namespace

using namespace datadog::conf;

const char* enable_rum_ddog(cmd_parms* /* cmd */, void* cfg, int value) {
  auto* dir_conf = static_cast<Directory*>(cfg);
  dir_conf->rum_enabled = (bool)value;
  return NULL;
}

const char* set_rum_json_conf(cmd_parms* cmd, void* cfg, const char* value) {
  auto* dir_conf = static_cast<Directory*>(cfg);

  auto json_content = read_file(value, cmd->pool);
  if (!json_content) {
    return apr_psprintf(cmd->pool, "failed to read RUM configuration \"%s\"",
                        value);
  }

  dir_conf->rum_json_configuration_content = *json_content;
  return NULL;
}
