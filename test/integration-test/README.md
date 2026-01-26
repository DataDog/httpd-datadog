# httpd-datadog Integration Tests

Integration tests for the Apache httpd Datadog module using pytest.

## Prerequisites

- **uv** - Fast Python package manager ([installation instructions](https://github.com/astral-sh/uv))
- **Apache httpd** with mod_datadog compiled
- **Docker** (optional, for containerized testing)

## Quick Start

### 1. Install uv

```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pip
pip install uv
```

### 2. Sync Dependencies

```bash
cd test/integration-test
uv sync
```

This will:
- Create a virtual environment (`.venv`)
- Install all dependencies from `pyproject.toml`
- Lock dependencies in `uv.lock`

### 3. Configure Paths

Set environment variables to avoid repeating paths:

```bash
export HTTPD_BIN_PATH=/path/to/apachectl
export HTTPD_MODULE_PATH=/path/to/mod_datadog.so
export TEST_LOG_DIR=/tmp/httpd-test-logs  # optional
```

Or pass them as command-line arguments to pytest.

### 4. Run Tests

```bash
# Run all tests (using environment variables)
uv run pytest

# Or with explicit paths
uv run pytest --bin-path=/path/to/apachectl --module-path=/path/to/mod_datadog.so

# Run specific test file
uv run pytest scenarios/test_rum.py -v

# Run specific test
uv run pytest scenarios/test_rum.py::test_rum_selective_disabling -vv

# Run with verbose output and show print statements
uv run pytest -vv -s
```

## Test Organization

```
integration-test/
├── conftest.py              # pytest configuration and fixtures
├── pytest_plugins/          # Custom pytest plugins
│   └── integration_helpers.py  # RUM detection and environment vars
├── pyproject.toml           # Project metadata and dependencies
├── scenarios/
│   ├── test_configuration.py   # Configuration directive tests
│   ├── test_smoke.py           # Basic functionality tests
│   ├── test_log_injection.py   # Log/trace correlation tests
│   ├── test_proxy.py           # Proxy forwarding tests
│   ├── test_rum.py             # RUM injection tests
│   ├── helper.py               # Test utilities
│   ├── conf/                   # Apache configuration templates
│   │   ├── default.conf
│   │   ├── directives.conf
│   │   ├── rum_selective.conf
│   │   └── ...
│   └── htdocs/                 # Test HTML files
│       ├── index.html
│       ├── app.html
│       ├── health.html
│       └── ...
└── README.md                # This file
```

## Test Markers

### Smoke Tests
Basic functionality tests marked with `@pytest.mark.smoke`:

```bash
uv run pytest -m smoke
```

### CI Tests
Tests suitable for CI environments marked with `@pytest.mark.ci`:

```bash
uv run pytest -m ci
```

### RUM Tests
RUM tests marked with `@pytest.mark.requires_rum`:

```bash
uv run pytest -m requires_rum
```

**Auto-Skip Behavior**: RUM tests automatically skip if:
- Module not compiled with `-DHTTPD_DATADOG_ENABLE_RUM=ON`
- `DatadogRum` directive not recognized

The RUM plugin detects support automatically at session start.

## RUM (Real User Monitoring) Tests

### Overview
RUM tests verify selective enabling/disabling of browser SDK injection using Apache's `<Location>` directives.

### Test Cases

1. **test_rum_selective_disabling** - Verify path-based RUM on/off
   - RUM enabled globally but disabled for `/health.html`, `/api.html`, `/static.html`
   - Verifies correct injection and non-injection

2. **test_rum_nested_location_override** - Verify nested location merging
   - Parent location `/app` has RUM enabled
   - Child location `/app/internal` disables RUM
   - Verifies child configuration overrides parent

3. **test_rum_configuration_validation** - Verify config syntax
   - Tests RUM configuration directives pass Apache validation

### RUM Configuration Example

```apache
# Enable RUM globally
DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "test-app-id-123"
  DatadogRumOption clientToken "test-client-token-456"
  DatadogRumOption site "datadoghq.com"
  DatadogRumOption service "rum-test-service"
  DatadogRumOption env "test"
  DatadogRumOption sessionSampleRate "100"
  DatadogRumOption trackUserInteractions "true"
</DatadogRumSettings>

# Disable RUM for specific paths
<Location "/health.html">
  DatadogRum Off
</Location>

<Location "/api.html">
  DatadogRum Off
</Location>
```

### Running RUM Tests

```bash
# Run all RUM tests
uv run pytest scenarios/test_rum.py -v

# Run specific RUM test
uv run pytest scenarios/test_rum.py::test_rum_selective_disabling -vv

# Run with debug output
uv run pytest scenarios/test_rum.py -vv -s
```

### RUM Implementation Details

**Filter Decision Logic** (mod_datadog/src/rum/filter.cpp):
1. Checks `dir_conf->rum.enabled` for the request path
2. Verifies Content-Type is `text/html`
3. Skips compressed content
4. Prevents double injection via `x-datadog-sdk-injected` header

**Configuration Merging** (mod_datadog/src/rum/config.cpp):
- Uses tri-state enabled field: -1 (not set), 0 (off), 1 (on)
- Child location configuration overrides parent
- Explicit `DatadogRum Off` in child disables even if parent enables

## Available Fixtures

Tests have access to these fixtures (defined in `conftest.py`):

- **`server`** - Apache server instance
  - `server.make_url(path)` - Create full URL for requests
  - `server.check_configuration(conf_path)` - Validate configuration
  - `server.load_configuration(conf_path)` - Start server with config
  - `server.stop(conf_path)` - Stop server
  - `server.check_directive(directive)` - Validate single directive

- **`agent`** - Test agent session for collecting traces
  - `agent.received_trace(timeout)` - Check if traces received
  - `agent.get_traces(timeout)` - Retrieve collected traces

- **`module_path`** - Path to `mod_datadog.so` module

- **`log_dir`** - Directory for test logs and temporary configs

## Docker Testing

### Build and Test with RUM Support

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace \
  datadog/docker-library:httpd-datadog-ci-2.4-cdb3cb2 \
  sh -c "
    # Build module with RUM support
    cmake -B build \
      -G Ninja \
      -DCMAKE_BUILD_TYPE=Debug \
      -DHTTPD_DATADOG_ENABLE_RUM=ON \
      .
    cmake --build build -j
    cmake --install build --prefix dist

    # Install Python dependencies and run tests
    pip install -r requirements.txt --break-system-packages
    pytest --bin-path=/httpd/httpd-build/bin/apachectl \
           --module-path=/workspace/dist/lib/mod_datadog.so \
           --log-dir=/workspace/test-logs \
           -v
  "
```

### Test Without RUM Support

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace \
  datadog/docker-library:httpd-datadog-ci-2.4-cdb3cb2 \
  sh -c "
    # Build module WITHOUT RUM support
    cmake -B build -G Ninja -DHTTPD_DATADOG_ENABLE_RUM=OFF .
    cmake --build build -j
    cmake --install build --prefix dist

    pip install -r requirements.txt --break-system-packages
    pytest --bin-path=/httpd/httpd-build/bin/apachectl \
           --module-path=/workspace/dist/lib/mod_datadog.so \
           -v
  "
# Expected: RUM tests will be skipped
```

## Development

### Adding Dependencies

```bash
# Add a new dependency
uv add package-name

# Add a dev dependency
uv add --dev package-name

# Update dependencies
uv lock --upgrade
```

### Running Tests in Parallel

```bash
# pytest-xdist is already in dev dependencies
uv run pytest scenarios/ -n auto
```

### Test Debugging

```bash
# Drop into debugger on failures
uv run pytest --pdb

# Show print statements
uv run pytest -s

# Show local variables on failure
uv run pytest -l

# Stop at first failure
uv run pytest -x

# Run last failed tests
uv run pytest --lf
```

## Custom Log Directory

Specify a custom directory for test logs:

```bash
uv run pytest --log-dir=/tmp/httpd-test-logs
# Or use environment variable
export TEST_LOG_DIR=/tmp/httpd-test-logs
uv run pytest
```

Logs include:
- `access_log` - Apache access logs
- `error_log` - Apache error logs (includes RUM injection debug messages)
- `httpd.conf` - Generated configuration file

## Troubleshooting

### Tests Hang or Timeout

The test agent runs on port 8136. Ensure it's not already in use:

```bash
lsof -i :8136
```

### Configuration Validation Fails

Check Apache configuration manually:

```bash
apachectl -f /path/to/test/config.conf -t
```

### Module Not Loading

Verify module path and dependencies:

```bash
ldd /path/to/mod_datadog.so
```

Ensure Apache has the required modules loaded (see `conftest.py` template).

### Test Agent Connection Issues

The test agent starts automatically during pytest session. If it fails:

1. Check if port 8136 is available
2. Look for errors in test output
3. Verify `ddapm-test-agent` is installed correctly:

```bash
uv run python -c "from ddapm_test_agent.agent import make_app; print('OK')"
```

### RUM Tests Skipped

If RUM tests are being skipped:

1. **Check module compilation**: Verify module was built with `-DHTTPD_DATADOG_ENABLE_RUM=ON`
2. **Verify RUM symbols**: Check if RUM code is in the module:
   ```bash
   strings dist/lib/mod_datadog.so | grep -i "inject.*browser"
   ```
3. **Check directive recognition**: Test manually:
   ```bash
   apachectl -C "LoadModule datadog_module /path/to/mod_datadog.so" -C "DatadogRum On" -t
   ```

### RUM Not Injecting (When Tests Run)

- Check Apache error logs for RUM filter messages
- Verify `DatadogRum On` is set in configuration
- Ensure RUM settings include: `applicationId`, `clientToken`, `site`
- Verify Content-Type is `text/html`
- Check response is not compressed

### RUM Injecting When It Shouldn't

- Verify `<Location>` directives match request paths exactly
- Check Apache's location matching rules (exact vs prefix)
- Review per-directory configuration merging logic

## CI Integration

Example GitHub Actions workflow:

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Build mod_datadog with RUM
        run: |
          cmake -B build -DHTTPD_DATADOG_ENABLE_RUM=ON .
          cmake --build build -j
          cmake --install build --prefix dist

      - name: Run integration tests
        run: |
          cd test/integration-test
          uv sync
          uv run pytest scenarios/ -m ci \
            --bin-path=/usr/bin/apachectl \
            --module-path=../../dist/lib/mod_datadog.so
```

## Writing New Tests

See `scenarios/test_rum.py` for examples. Basic pattern:

```python
import pytest
from helper import make_configuration, save_configuration, relpath

def test_example(server, agent, log_dir, module_path):
    # 1. Create configuration
    config = {
        "path": relpath("conf/example.conf"),
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    # 2. Validate and load
    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    # 3. Make requests
    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200

    # 4. Stop server
    assert server.stop(conf_path)

    # 5. Verify traces (optional)
    traces = agent.get_traces(timeout=5)
    assert len(traces) >= 1
```

### Writing RUM Tests

Mark tests that require RUM support:

```python
@pytest.mark.requires_rum
def test_rum_feature(server, agent, log_dir, module_path):
    """Test will auto-skip if RUM not compiled."""
    # Test implementation...
```

## Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [pytest Documentation](https://docs.pytest.org/)
- [ddapm-test-agent](https://github.com/DataDog/dd-apm-test-agent)
- [Apache httpd Documentation](https://httpd.apache.org/docs/)
- [Datadog RUM Documentation](https://docs.datadoghq.com/real_user_monitoring/)
