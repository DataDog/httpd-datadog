The header tests run with `build/test/unit-test/tests`.

The directory lifetime check needs native APR and APR-util libraries. Build it
with its AddressSanitizer target to check pool cleanup and RUM snippet ownership:

```sh
cmake -S . -B build -DHTTPD_SRC_DIR=/path/to/httpd \
  -DHTTPD_DATADOG_ENABLE_RUM=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build --target directory_lifetime_tests -j2
ASAN_OPTIONS=detect_leaks=1 ctest --test-dir build -R directory-lifetime \
  --output-on-failure
```

Use `HTTPD_DATADOG_ENABLE_RUM=OFF` to check tracing-only configs as well.
