# CLAUDE.md

## Building and Testing

Initialize the project submodules before building. The private
`inject-browser-sdk` submodule is required for RUM builds.

```bash
git submodule update --init --recursive
make ci-build              # Non-RUM CI build
make test-integration      # RUM-enabled build and integration tests
make dev-shell             # Interactive devcontainer shell
```

The devcontainer image is selected for the host architecture and includes the
LLVM toolchain, httpd source, Rust, and uv.

### Running specific tests inside Docker

```bash
make dev-shell
# Inside container:
.devcontainer/run-integration-tests.sh \
  scenarios/test_rum.py::test_rum_selective_disabling -m requires_rum
```

### Key paths inside the CI image

- `/httpd` — httpd source
- `/httpd/httpd-build/bin/apachectl` — pre-built apachectl binary
- `/sysroot/{arch}-none-linux-musl/Toolchain.cmake` — cross-compilation toolchain

### Test markers

- `requires_rum` — tests needing RUM-enabled build (`-DHTTPD_DATADOG_ENABLE_RUM=ON`)
- Tests without markers run against the standard build

## CI/CD

GitLab CI status can be checked via `glab ci` on the automated mirror:
https://gitlab.ddbuild.io/DataDog/httpd-datadog/
