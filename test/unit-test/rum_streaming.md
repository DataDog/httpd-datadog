Build the streaming checks with RUM and native APR/APR-util libraries:

```sh
cmake -S . -B build -DHTTPD_SRC_DIR=/path/to/httpd \
  -DHTTPD_DATADOG_ENABLE_RUM=ON
cmake --build build --target rum_streaming_tests -j2
ctest --test-dir build -R rum-streaming --output-on-failure
```

These checks run the real filter with the pinned injector and APR buckets under
AddressSanitizer. They cover every split in a short HTML body, multiple buckets
in one brigade, false closing tags, EOF with a partial tag, flush buckets, and
downstream reads delayed until the filter has processed all input.
