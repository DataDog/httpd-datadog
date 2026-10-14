HTTP checks run in the RUM and integration CI jobs. From `test/integration-test`:
`uv run pytest scenarios/test_rum_streaming.py --module-path=/path/to/mod_datadog.so --bin-path=/path/to/apachectl -v`

```sh
cmake -S . -B build -DHTTPD_SRC_DIR=/path/to/httpd -DHTTPD_DATADOG_ENABLE_RUM=ON
cmake --build build --target rum_streaming_tests -j2
ASAN_OPTIONS=detect_leaks=1 ctest --test-dir build -R rum-streaming --output-on-failure
```

Native ASAN checks need APR/APR-util and verify split input, EOF, deferred reads,
flush/EOS order, and 200 KB slices. Musl CI runs only the HTTP checks.
The pinned injector pads skipped HTML with snippet-sized spaces.
