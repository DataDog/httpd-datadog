# httpd-datadog Integration Tests

Integration tests for Apache httpd Datadog module using pytest.

## Quick Start

### Prerequisites

For local testing, install Apache development packages:
```bash
# Ubuntu/Debian
sudo apt-get install apache2 apache2-dev libapr1-dev libaprutil1-dev

# macOS
brew install httpd
```

### Setup

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install test dependencies
cd test/integration-test && uv sync

# Run all tests (auto-builds module variants as needed)
uv run pytest --bin-path=/usr/sbin/apachectl -v

# Run RUM tests only (auto-builds with RUM support)
uv run pytest --bin-path=/usr/sbin/apachectl -m requires_rum -v

# Run with pre-built module (skip auto-build)
uv run pytest --bin-path=/usr/sbin/apachectl \
  --module-path=/path/to/mod_datadog.so -v

# Run specific test file
uv run pytest --bin-path=/usr/sbin/apachectl \
  scenarios/test_rum.py -v
```

**Auto-Build Behavior:**
- The test suite automatically builds two module variants on demand:
  - **Without RUM**: `build/mod_datadog/mod_datadog.so` (for regular tests)
  - **With RUM**: `build-rum/mod_datadog/mod_datadog.so` (for `@pytest.mark.requires_rum` tests)
- Each variant is only built if tests requiring it are collected
- Tests automatically use the correct variant based on markers
- Build failures cause tests to fail (not skip)
- Use `--module-path` to override and skip auto-build

## Command-Line Options

Required options:
- `--bin-path` - Path to apachectl binary (e.g., `/usr/sbin/apachectl`)

Optional:
- `--module-path` - Path to mod_datadog.so (skips auto-build if provided)
- `--log-dir` - Directory for test logs (defaults to temp directory)

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
    cd test/integration-test
    pip install -r requirements.txt --break-system-packages
    uv run pytest --bin-path=/httpd/httpd-build/bin/apachectl \
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
