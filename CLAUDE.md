# CLAUDE.md

## Building and Testing

Building requires the CI Docker image (Alpine with LLVM toolchain, httpd source, Rust, uv).
The image is auto-detected for the host architecture (arm64/amd64).

```bash
make vendor                # Pre-fetch RUM deps (corrosion, inject-browser-sdk) to vendor/
make docker-build          # Build mod_datadog.so (no RUM)
make docker-build-rum      # Build mod_datadog.so with RUM (runs vendor automatically)
make docker-test           # Build + run all integration tests (non-RUM)
make docker-test-rum       # Build + run RUM integration tests
make docker-shell          # Interactive shell in the CI image
```

RUM builds use vendored dependencies (`vendor/` directory) so Docker doesn't need
network access to private repos. `make docker-build-rum` runs `make vendor` automatically.
To refresh vendored deps: `rm -rf vendor && make vendor`.

### Running specific tests inside Docker

```bash
make docker-shell
# Inside container:
cmake -B build-rum -DCMAKE_TOOLCHAIN_FILE=/sysroot/aarch64-none-linux-musl/Toolchain.cmake \
  -DHTTPD_SRC_DIR=/httpd -DHTTPD_DATADOG_PATCH_AWAY_LIBC=1 -DHTTPD_DATADOG_ENABLE_RUM=ON -G Ninja .
cmake --build build-rum -j
cd test/integration-test && uv sync
uv run pytest scenarios/test_rum.py::test_rum_selective_disabling \
  --module-path /src/build-rum/mod_datadog/mod_datadog.so \
  --bin-path /httpd/httpd-build/bin/apachectl \
  --log-dir /src/logs -m requires_rum -v
```

### Key paths inside the CI image

- `/httpd` — httpd source (used by `-DHTTPD_SRC_DIR`)
- `/httpd/httpd-build/bin/apachectl` — pre-built apachectl binary
- `/sysroot/{arch}-none-linux-musl/Toolchain.cmake` — cross-compilation toolchain

### Test markers

- `requires_rum` — tests needing RUM-enabled build (`-DHTTPD_DATADOG_ENABLE_RUM=ON`)
- Tests without markers run against the standard build

## CI/CD

GitLab CI status can be checked via `glab ci` on the automated mirror:
https://gitlab.ddbuild.io/DataDog/httpd-datadog/
