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

namespace {

enum class Brigades { separate, single };
enum class Reads { immediate, deferred };
enum class Flushes { none, after_each_chunk };

struct Downstream {
  apr_bucket_brigade* brigade = nullptr;
  Reads reads = Reads::immediate;
  std::string output;
  std::vector<size_t> flush_offsets;
  int endings = 0;
};

Downstream downstream;

// Called from the filter: use CHECK, so a failure does not throw through it.
void read_output() {
  for (apr_bucket* bucket = APR_BRIGADE_FIRST(downstream.brigade);
       bucket != APR_BRIGADE_SENTINEL(downstream.brigade);
       bucket = APR_BUCKET_NEXT(bucket)) {
    CHECK(downstream.endings == 0);
    if (APR_BUCKET_IS_EOS(bucket)) ++downstream.endings;
    if (APR_BUCKET_IS_FLUSH(bucket)) {
      downstream.flush_offsets.push_back(downstream.output.size());
    }
    if (APR_BUCKET_IS_METADATA(bucket)) continue;
    const char* buffer = nullptr;
    apr_size_t length = 0;
    const apr_status_t status =
        apr_bucket_read(bucket, &buffer, &length, APR_BLOCK_READ);
    CHECK(status == APR_SUCCESS);
    downstream.output.append(buffer, length);
  }
  apr_brigade_cleanup(downstream.brigade);
}

}  // namespace

extern "C" apr_status_t ap_pass_brigade(ap_filter_t*,
                                        apr_bucket_brigade* brigade) {
  APR_BRIGADE_CONCAT(downstream.brigade, brigade);
  if (downstream.reads == Reads::immediate) read_output();
  return APR_SUCCESS;
}

namespace {

std::string snippet_text(Snippet* snippet) {
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

std::string write_stream(ap_filter_t* filter, apr_bucket_brigade* brigade,
                         const std::vector<std::string>& chunks,
                         Brigades brigades, Flushes flushes) {
  std::string expected;
  for (const std::string& chunk : chunks) {
    expected += chunk;
    APR_BRIGADE_INSERT_TAIL(
        brigade, apr_bucket_heap_create(chunk.data(), chunk.size(), nullptr,
                                        filter->c->bucket_alloc));
    if (flushes == Flushes::after_each_chunk) {
      APR_BRIGADE_INSERT_TAIL(brigade,
                              apr_bucket_flush_create(filter->c->bucket_alloc));
    }
    if (brigades == Brigades::separate) {
      CHECK(rum_output_filter(filter, brigade) == APR_SUCCESS);
    }
  }
  APR_BRIGADE_INSERT_TAIL(brigade,
                          apr_bucket_eos_create(filter->c->bucket_alloc));
  CHECK(rum_output_filter(filter, brigade) == APR_SUCCESS);
  read_output();
  return expected;
}

void check_output(std::string expected, const std::string& snippet) {
  const size_t closing = expected.find("</head>");
  if (closing == std::string::npos) {
    expected.append(snippet.size(), ' ');
  } else {
    expected.insert(closing, snippet);
  }
  CHECK(downstream.output == expected);
  CHECK(downstream.endings == 1);
}

// Returns the snippet text, so callers can check positions in the output.
std::string check_stream(const std::vector<std::string>& chunks,
                         Brigades brigades = Brigades::separate,
                         Reads reads = Reads::immediate,
                         Flushes flushes = Flushes::none) {
  datadog::conf::Directory directory;
  directory.rum.enabled = true;
  directory.rum.snippet = snippet_create_from_json(
      "{\"majorVersion\":6,\"rum\":{\"applicationId\":\"test\","
      "\"clientToken\":\"test\"}}");
  REQUIRE(directory.rum.snippet->error_code == 0);
  const std::string snippet = snippet_text(directory.rum.snippet);

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
  void* configuration[] = {&directory};
  request.per_dir_config = reinterpret_cast<ap_conf_vector_t*>(configuration);
  ap_filter_t filter = {};
  filter.r = &request;
  filter.c = &connection;
  downstream = {};
  downstream.brigade = apr_brigade_create(pool, connection.bucket_alloc);
  downstream.reads = reads;
  apr_bucket_brigade* brigade =
      apr_brigade_create(pool, connection.bucket_alloc);
  check_output(write_stream(&filter, brigade, chunks, brigades, flushes),
               snippet);
  apr_pool_destroy(pool);
  apr_terminate();
  return snippet;
}

}  // namespace

TEST_CASE("RUM injects when the closing tag is split across buckets", "[rum]") {
  const Brigades brigades = GENERATE(Brigades::separate, Brigades::single);
  const std::string body = "abc</head>def";
  for (size_t split = 1; split < body.size(); ++split) {
    INFO("split at " << split
                     << (brigades == Brigades::single ? ", same brigade" : ""));
    check_stream({body.substr(0, split), body.substr(split)}, brigades);
  }
}

TEST_CASE("RUM keeps a false prefix of the closing tag", "[rum]") {
  check_stream({"abc</he", "ader>def"});
}

TEST_CASE("RUM keeps a partial closing tag at the end of the stream", "[rum]") {
  check_stream({"abc</he"});
}

TEST_CASE("RUM output stays valid when downstream reads later", "[rum]") {
  check_stream({"abc</he", "ader>def</he", "ad>tail", "after"},
               Brigades::separate, Reads::deferred);
}

TEST_CASE("RUM injects into a large response", "[rum]") {
  check_stream(
      {std::string(100000, 'x') + "</head>" + std::string(100000, 'y')},
      Brigades::single, Reads::deferred);
}

TEST_CASE("RUM keeps flush buckets at their position", "[rum]") {
  const std::string partial_tag = "</he";
  const std::vector<std::string> chunks = {"abc" + partial_tag, "ad>", "def"};
  const std::string snippet = check_stream(
      chunks, Brigades::separate, Reads::immediate, Flushes::after_each_chunk);
  // The partial tag is held back until the next chunk.
  const size_t head = chunks[0].size() + chunks[1].size();
  const std::vector<size_t> expected = {
      chunks[0].size() - partial_tag.size(), snippet.size() + head,
      snippet.size() + head + chunks[2].size()};
  CHECK(downstream.flush_offsets == expected);
}
