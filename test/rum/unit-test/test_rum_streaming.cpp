// clang-format off
#include "httpd.h"
// clang-format on
#include <apr_general.h>
#include <http_log.h>
#include <util_filter.h>

#include <catch2/catch.hpp>
#include <string>
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

// Called from the filter: use CHECK, so a failure does not throw through it.
static void read_output() {
  for (apr_bucket* bucket = APR_BRIGADE_FIRST(downstream);
       bucket != APR_BRIGADE_SENTINEL(downstream);
       bucket = APR_BUCKET_NEXT(bucket)) {
    CHECK(endings == 0);
    if (APR_BUCKET_IS_EOS(bucket)) ++endings;
    if (APR_BUCKET_IS_FLUSH(bucket)) flush_offsets.push_back(output.size());
    if (APR_BUCKET_IS_METADATA(bucket)) continue;
    const char* buffer = nullptr;
    apr_size_t length = 0;
    const apr_status_t status =
        apr_bucket_read(bucket, &buffer, &length, APR_BLOCK_READ);
    CHECK(status == APR_SUCCESS);
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
  const InjectorResult result = injector_write(
      injector, reinterpret_cast<const uint8_t*>(closing_tag.data()),
      closing_tag.size());
  std::string text;
  for (size_t index = 0; index < result.slices_length; ++index) {
    text.append(reinterpret_cast<const char*>(result.slices[index].start),
                result.slices[index].length);
  }
  const bool injected = result.injected;
  injector_cleanup(injector);
  REQUIRE(injected);
  text.resize(text.size() - closing_tag.size());
  return text;
}

static std::string write_stream(ap_filter_t* filter,
                                apr_bucket_brigade* brigade,
                                const std::vector<std::string>& chunks,
                                bool together, bool with_flush) {
  std::string expected;
  for (const std::string& chunk : chunks) {
    expected += chunk;
    APR_BRIGADE_INSERT_TAIL(
        brigade, apr_bucket_heap_create(chunk.data(), chunk.size(), nullptr,
                                        filter->c->bucket_alloc));
    if (with_flush) {
      APR_BRIGADE_INSERT_TAIL(brigade,
                              apr_bucket_flush_create(filter->c->bucket_alloc));
    }
    if (!together) CHECK(rum_output_filter(filter, brigade) == APR_SUCCESS);
  }
  APR_BRIGADE_INSERT_TAIL(brigade,
                          apr_bucket_eos_create(filter->c->bucket_alloc));
  CHECK(rum_output_filter(filter, brigade) == APR_SUCCESS);
  read_output();
  return expected;
}

static void check_output(std::string expected, const std::string& snippet) {
  const size_t closing = expected.find("</head>");
  if (closing == std::string::npos) {
    expected.append(snippet.size(), ' ');
  } else {
    expected.insert(closing, snippet);
  }
  CHECK(output == expected);
  CHECK(endings == 1);
}

// Returns the snippet text, so callers can check positions in the output.
static std::string check_stream(const std::vector<std::string>& chunks,
                                bool together, bool deferred,
                                bool with_flush = false) {
  defer_reads = deferred;
  apr_initialize();
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
  directory.rum.snippet = snippet_create_from_json(
      "{\"majorVersion\":6,\"rum\":{\"applicationId\":\"test\","
      "\"clientToken\":\"test\"}}");
  CHECK(directory.rum.snippet->error_code == 0);
  const std::string snippet = snippet_text(directory.rum.snippet);
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
  check_output(write_stream(&filter, brigade, chunks, together, with_flush),
               snippet);
  apr_pool_destroy(pool);
  apr_terminate();
  return snippet;
}

TEST_CASE("RUM injects when the closing tag is split across buckets", "[rum]") {
  const bool together = GENERATE(false, true);
  const std::string body = "abc</head>def";
  for (size_t split = 1; split < body.size(); ++split) {
    INFO("split at " << split << (together ? ", same brigade" : ""));
    check_stream({body.substr(0, split), body.substr(split)}, together, false);
  }
}

TEST_CASE("RUM keeps a false prefix of the closing tag", "[rum]") {
  check_stream({"abc</he", "ader>def"}, false, false);
}

TEST_CASE("RUM keeps a partial closing tag at the end of the stream", "[rum]") {
  check_stream({"abc</he"}, false, false);
}

TEST_CASE("RUM output stays valid when downstream reads later", "[rum]") {
  check_stream({"abc</he", "ader>def</he", "ad>tail", "after"}, false, true);
}

TEST_CASE("RUM injects into a large response", "[rum]") {
  check_stream(
      {std::string(100000, 'x') + "</head>" + std::string(100000, 'y')}, true,
      true);
}

TEST_CASE("RUM keeps flush buckets at their position", "[rum]") {
  const std::string snippet =
      check_stream({"abc</he", "ad>", "def"}, false, false, true);
  const std::vector<size_t> expected = {3, 10 + snippet.size(),
                                        13 + snippet.size()};
  CHECK(flush_offsets == expected);
}
