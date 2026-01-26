# httpd-datadog Integration Tests

Integration tests for Apache httpd Datadog module using pytest.

## Quick Start

```bash
# Install dependencies
curl -LsSf https://astral.sh/uv/install.sh | sh
cd test/integration-test && uv sync

# Set paths
export HTTPD_BIN_PATH=/path/to/apachectl
export HTTPD_MODULE_PATH=/path/to/mod_datadog.so

# Run tests
uv run pytest

# Run specific tests
uv run pytest scenarios/test_rum.py -v
uv run pytest -m smoke
```

## Environment Variables

- `HTTPD_BIN_PATH` - Path to apachectl binary
- `HTTPD_MODULE_PATH` - Path to mod_datadog.so
- `TEST_LOG_DIR` - (Optional) Directory for test logs

## Test Markers

- `@pytest.mark.smoke` - Basic functionality tests
- `@pytest.mark.ci` - CI-suitable tests
- `@pytest.mark.requires_rum` - RUM tests (auto-skip if RUM not compiled)

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
- Auto-skip when module lacks `-DHTTPD_DATADOG_ENABLE_RUM=ON`

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

**RUM tests skipped:** Module not built with `-DHTTPD_DATADOG_ENABLE_RUM=ON`
```bash
strings dist/lib/mod_datadog.so | grep -i "inject.*browser"
```

**Tests hang:** Port 8136 in use
```bash
lsof -i :8136
```

**Module issues:**
```bash
ldd /path/to/mod_datadog.so
apachectl -f /path/to/config.conf -t
```
