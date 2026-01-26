# httpd-datadog Integration Tests

Integration tests for the Apache httpd Datadog module using pytest.

## Prerequisites

- **uv** - Fast Python package manager ([installation instructions](https://github.com/astral-sh/uv))
- **Apache httpd** with mod_datadog compiled
- **Docker** (optional, for running test agent in container)

## Quick Start with uv

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

### 3. Run Tests

```bash
# Run all tests
uv run pytest scenarios/ \
  --bin-path=/path/to/apachectl \
  --module-path=/path/to/mod_datadog.so

# Run specific test file
uv run pytest scenarios/test_rum.py \
  --bin-path=/path/to/apachectl \
  --module-path=/path/to/mod_datadog.so

# Run specific test
uv run pytest scenarios/test_rum.py::test_rum_selective_disabling \
  --bin-path=/path/to/apachectl \
  --module-path=/path/to/mod_datadog.so

# Run with more verbose output
uv run pytest scenarios/test_rum.py -vv -s \
  --bin-path=/path/to/apachectl \
  --module-path=/path/to/mod_datadog.so
```

### 4. Using Environment Variables

To avoid typing paths repeatedly, create a `.env` file or export variables:

```bash
export HTTPD_BIN_PATH=/usr/local/apache2/bin/apachectl
export HTTPD_MODULE_PATH=/path/to/mod_datadog.so

# Then run tests without path arguments
uv run pytest scenarios/ \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH
```

## Test Organization

```
integration-test/
├── conftest.py           # pytest configuration and fixtures
├── pytest.ini            # pytest settings (legacy, migrated to pyproject.toml)
├── pyproject.toml        # Project metadata and dependencies
├── docker-compose.yaml   # Docker services (httpd + test agent)
├── scenarios/
│   ├── test_configuration.py   # Configuration directive tests
│   ├── test_smoke.py           # Basic functionality tests
│   ├── test_log_injection.py   # Log/trace correlation tests
│   ├── test_proxy.py           # Proxy forwarding tests
│   ├── test_rum.py             # RUM injection tests
│   ├── helper.py               # Test utilities
│   ├── conf/                   # Apache configuration files
│   │   ├── default.conf
│   │   ├── directives.conf
│   │   ├── rum_selective.conf
│   │   └── ...
│   └── htdocs/                 # Test HTML files
│       ├── index.html
│       ├── app.html
│       ├── health.html
│       └── ...
└── README.md            # This file
```

## Test Types

### Smoke Tests
Basic functionality tests marked with `@pytest.mark.smoke`:

```bash
uv run pytest -m smoke \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH
```

### CI Tests
Tests suitable for CI environments marked with `@pytest.mark.ci`:

```bash
uv run pytest -m ci \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH
```

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

## Running with Docker

The `docker-compose.yaml` provides a containerized environment:

```bash
# Start services
docker-compose up -d

# Run tests against containerized Apache
uv run pytest scenarios/ \
  --bin-path=docker-compose exec httpd apachectl \
  --module-path=/path/to/mod_datadog.so

# Stop services
docker-compose down
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

Install the parallel execution plugin:

```bash
uv add pytest-xdist
```

Run tests in parallel:

```bash
uv run pytest scenarios/ -n auto \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH
```

### Test Debugging

```bash
# Drop into debugger on failures
uv run pytest scenarios/ --pdb \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH

# Show print statements
uv run pytest scenarios/ -s \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH

# Show local variables on failure
uv run pytest scenarios/ -l \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH
```

## Custom Log Directory

Specify a custom directory for test logs:

```bash
uv run pytest scenarios/ \
  --bin-path=$HTTPD_BIN_PATH \
  --module-path=$HTTPD_MODULE_PATH \
  --log-dir=/tmp/httpd-test-logs
```

Logs include:
- `access_log` - Apache access logs
- `error_log` - Apache error logs
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

      - name: Build mod_datadog
        run: |
          # Your build steps here
          cmake ...
          make

      - name: Run integration tests
        run: |
          cd test/integration-test
          uv sync
          uv run pytest scenarios/ -m ci \
            --bin-path=/usr/bin/apachectl \
            --module-path=../../build/mod_datadog.so
```

## Writing New Tests

See `scenarios/test_rum.py` for examples. Basic pattern:

```python
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

    # 5. Verify traces
    traces = agent.get_traces(timeout=5)
    assert len(traces) >= 1
```

## Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [pytest Documentation](https://docs.pytest.org/)
- [ddapm-test-agent](https://github.com/DataDog/dd-apm-test-agent)
- [Apache httpd Documentation](https://httpd.apache.org/docs/)
