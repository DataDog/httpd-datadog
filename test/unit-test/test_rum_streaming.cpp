// clang-format off
#include "httpd.h"
// clang-format on
#include <apr_general.h>
#include <http_log.h>
#include <util_filter.h>

#include <cassert>
#include <memory>
#include <string>
#include <type_traits>
#include <vector>

#include "common_conf.h"
#include "rum/filter.h"
#include "rum/telemetry.h"

module datadog_module = {};
extern const std::string_view mod_datadog_version = "test";
extern const std::string_view datadog_rum_injector_version = "test";

namespace datadog::telemetry::counter {
void increment(const Counter&, const std::vector<std::string>&) {}
}  // namespace datadog::telemetry::counter

extern "C" {
void ap_log_rerror_(const char*, int, int, int, apr_status_t,
                    const request_rec*, const char*, ...) {}
#ifndef ap_get_request_module_loglevel
int ap_get_request_module_loglevel(const request_rec*, int) { return 0; }
#endif
}

static apr_bucket_brigade* downstream = nullptr;
static std::string output;
static bool defer_reads = false;
static std::vector<size_t> flush_offsets;
static int endings = 0;

static void read_output() {
  for (apr_bucket* bucket = APR_BRIGADE_FIRST(downstream);
       bucket != APR_BRIGADE_SENTINEL(downstream);
       bucket = APR_BUCKET_NEXT(bucket)) {
    assert(endings == 0);
    if (APR_BUCKET_IS_EOS(bucket)) ++endings;
    if (APR_BUCKET_IS_FLUSH(bucket)) flush_offsets.push_back(output.size());
    if (APR_BUCKET_IS_METADATA(bucket)) continue;
    const char* buffer = nullptr;
    apr_size_t length = 0;
    assert(apr_bucket_read(bucket, &buffer, &length, APR_BLOCK_READ) ==
           APR_SUCCESS);
    output.append(buffer, length);
  }
  apr_brigade_cleanup(downstream);
}

extern "C" apr_status_t ap_pass_brigade(ap_filter_t*,
                                        apr_bucket_brigade* brigade) {
  APR_BRIGADE_CONCAT(downstream, brigade);
  if (!defer_reads) read_output();
  return APR_SUCCESS;
}

static std::string snippet_text(Snippet* snippet) {
  Injector* injector = injector_create(snippet);
  const std::string closing_tag = "</head>";
  InjectorResult result = injector_write(
      injector, reinterpret_cast<const uint8_t*>(closing_tag.data()),
      closing_tag.size());
  std::string text;
  for (size_t index = 0; index < result.slices_length; ++index) {
    text.append(reinterpret_cast<const char*>(result.slices[index].start),
                result.slices[index].length);
  }
  assert(result.injected);
  injector_cleanup(injector);
  text.resize(text.size() - closing_tag.size());
  return text;
}

template <typename SnippetOwner>
static void own_snippet(SnippetOwner& owner, Snippet* snippet) {
  if constexpr (std::is_pointer_v<SnippetOwner>) {
    owner = snippet;
  } else {
    owner = std::shared_ptr<Snippet>(snippet, snippet_cleanup);
  }
}

static void check_stream(const std::vector<std::string>& chunks, bool together,
                         bool with_flush = false) {
  apr_pool_t* pool = nullptr;
  apr_pool_create(&pool, nullptr);
  conn_rec connection = {};
  connection.bucket_alloc = apr_bucket_alloc_create(pool);
  request_rec request = {};
  server_rec server = {};
  request.server = &server;
  request.pool = pool;
  request.connection = &connection;
  request.content_type = "text/html";
  request.headers_out = apr_table_make(pool, 4);
  datadog::conf::Directory directory;
  directory.rum.enabled = true;
  Snippet* snippet_pointer = snippet_create_from_json(
      "{\"majorVersion\":6,\"rum\":{\"applicationId\":\"test\","
      "\"clientToken\":\"test\"}}");
  own_snippet(directory.rum.snippet, snippet_pointer);
  assert(snippet_pointer->error_code == 0);
  const std::string snippet = snippet_text(snippet_pointer);
  void* configuration[] = {&directory};
  request.per_dir_config = reinterpret_cast<ap_conf_vector_t*>(configuration);
  ap_filter_t filter = {};
  filter.r = &request;
  filter.c = &connection;
  downstream = apr_brigade_create(pool, connection.bucket_alloc);
  apr_bucket_brigade* brigade =
      apr_brigade_create(pool, connection.bucket_alloc);
  output.clear();
  flush_offsets.clear();
  endings = 0;
  std::string expected;
  for (const std::string& chunk : chunks) {
    expected += chunk;
    APR_BRIGADE_INSERT_TAIL(
        brigade, apr_bucket_heap_create(chunk.data(), chunk.size(), nullptr,
                                        connection.bucket_alloc));
    if (with_flush) {
      APR_BRIGADE_INSERT_TAIL(brigade,
                              apr_bucket_flush_create(connection.bucket_alloc));
    }
    if (!together) assert(rum_output_filter(&filter, brigade) == APR_SUCCESS);
  }
  APR_BRIGADE_INSERT_TAIL(brigade,
                          apr_bucket_eos_create(connection.bucket_alloc));
  assert(rum_output_filter(&filter, brigade) == APR_SUCCESS);
  read_output();
  const size_t closing = expected.find("</head>");
  if (closing == std::string::npos) {
    expected.append(snippet.size(), ' ');
  } else {
    expected.insert(closing, snippet);
  }
  assert(output == expected);
  assert(endings == 1);
  if (with_flush) {
    const std::vector<size_t> expected_offsets = {3, 10 + snippet.size(),
                                                  expected.size()};
    assert(flush_offsets == expected_offsets);
  }
  apr_pool_destroy(pool);
}

int main(int argc, char* argv[]) {
  assert(argc == 2);
  apr_initialize();
  const std::string mode = argv[1];
  defer_reads = mode == "deferred" || mode == "large";
  if (mode == "false-prefix") {
    check_stream({"abc</he", "ader>def"}, false);
  } else if (mode == "eof") {
    check_stream({"abc</he"}, false);
  } else if (mode == "deferred") {
    check_stream({"abc</he", "ader>def</he", "ad>tail", "after"}, false);
  } else if (mode == "large") {
    check_stream(
        {std::string(100000, 'x') + "</head>" + std::string(100000, 'y')},
        true);
  } else if (mode == "flush") {
    check_stream({"abc</he", "ad>", "def"}, false, true);
  } else {
    const std::string body = "abc</head>def";
    for (size_t split = 1; split < body.size(); ++split) {
      check_stream({body.substr(0, split), body.substr(split)},
                   mode == "same-brigade");
    }
  }
  apr_terminate();
}
