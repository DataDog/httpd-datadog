The HTTP regression runs in the existing RUM and integration CI jobs:

```sh
cd test/integration-test
uv run pytest scenarios/test_rum_streaming.py \
  --module-path=/path/to/mod_datadog.so --bin-path=/path/to/apachectl -v
```

It checks split tags, false prefixes, EOF, and a 100 KB response through Apache.
Build the bucket lifetime checks with RUM and native APR/APR-util libraries:

```sh
cmake -S . -B build -DHTTPD_SRC_DIR=/path/to/httpd \
  -DHTTPD_DATADOG_ENABLE_RUM=ON
cmake --build build --target rum_streaming_tests -j2
ASAN_OPTIONS=detect_leaks=1 ctest --test-dir build -R rum-streaming --output-on-failure
```

These seven checks use the pinned injector under AddressSanitizer. They verify
split buckets and brigades, false prefixes, EOF, delayed reads, flush positions,
a final EOS, and a 200 KB bucket. The native target is not built by musl CI.
The pinned injector adds snippet-sized spaces when no closing tag is found.
