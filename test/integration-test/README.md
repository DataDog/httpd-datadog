# httpd-datadog Integration Tests

Integration tests for Apache httpd Datadog module using pytest.

## Quick Start

```bash
# Install dependencies
curl -LsSf https://astral.sh/uv/install.sh | sh
cd test/integration-test && uv sync

# Set Apache path and run tests
export HTTPD_BIN_PATH=/path/to/apachectl
uv run pytest

# Run specific tests
uv run pytest scenarios/test_rum.py -v  # Auto-builds with RUM
uv run pytest -m smoke
```

**Auto-Build Behavior:**
- The test suite automatically builds two module variants on demand:
  - **Without RUM**: `build/mod_datadog/mod_datadog.so` (for regular tests)
  - **With RUM**: `build-rum/mod_datadog/mod_datadog.so` (for `@pytest.mark.requires_rum` tests)
- Each variant is only built if tests requiring it are collected
- Tests automatically use the correct variant based on markers
- Build failures cause tests to fail (not skip)
- Use `--module-path` to override and skip auto-build

## Environment Variables

- `HTTPD_BIN_PATH` - Path to apachectl binary (required)
- `HTTPD_MODULE_PATH` - Path to mod_datadog.so (auto-built for RUM tests)
- `TEST_LOG_DIR` - Directory for test logs (optional)

## Test Markers

- `@pytest.mark.smoke` - Basic functionality tests
- `@pytest.mark.ci` - CI-suitable tests
- `@pytest.mark.requires_rum` - RUM tests (auto-build module with RUM)

## RUM Tests

RUM tests verify selective browser SDK injection using Apache `<Location>` directives.

**Configuration Example:**
```apache
DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "app-id"
  DatadogRumOption clientToken "token"
  DatadogRumOption site "datadoghq.com"
</DatadogRumSettings>

<Location "/health.html">
  DatadogRum Off
</Location>
```

**Implementation:**
- Uses tri-state: -1 (not set), 0 (off), 1 (on)
- Child `<Location>` overrides parent
- Auto-builds module with `-DHTTPD_DATADOG_ENABLE_RUM=ON` when RUM tests detected

## Docker Testing

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace \
  datadog/docker-library:httpd-datadog-ci-2.4-cdb3cb2 \
  sh -c "
    cmake -B build -G Ninja -DHTTPD_DATADOG_ENABLE_RUM=ON .
    cmake --build build -j && cmake --install build --prefix dist
    pip install -r requirements.txt --break-system-packages
    pytest --bin-path=/httpd/httpd-build/bin/apachectl \
           --module-path=/workspace/dist/lib/mod_datadog.so -v
  "
```

## Troubleshooting

**RUM build fails:** Check CMake output for missing dependencies (inject-browser-sdk is fetched automatically via CMake FetchContent)

**Tests hang:** Port 8136 in use
```bash
lsof -i :8136
```

**Module issues:**
```bash
ldd /path/to/mod_datadog.so
apachectl -f /path/to/config.conf -t
```
