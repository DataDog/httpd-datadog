# httpd-datadog Integration Tests

Integration tests for Apache httpd Datadog module using pytest.

## All Tests

All the commands below must be run from the root the repository, not from the `test/integration-test` directory:

```sh
cd httpd-datadog
```

### Pre-requisites

```sh
git submodule update --init --recursive
cmake --build build-rum  # populates build-rum/_deps/injectbrowsersdk-src/
```

### Build the Docker Image

```sh
docker build -f test/integration-test/Dockerfile -t httpd-datadog-tests .
```

### Run All Tests

```sh
docker run --rm httpd-datadog-tests
```

### Run Tests by Markers

The tests have the following optional markers:

- `@pytest.mark.smoke` - Basic functionality tests
- `@pytest.mark.ci` - CI-suitable tests
- `@pytest.mark.requires_rum` - RUM tests (auto-build module with RUM)

So, to run only smoke tests:

```sh
docker run --rm httpd-datadog-tests uv run pytest --bin-path=/httpd/httpd-build/bin/apachectl -v -m smoke
```

Similarly, to run only CI tests:

```sh
docker run --rm httpd-datadog-tests uv run pytest --bin-path=/httpd/httpd-build/bin/apachectl -v -m ci
```

### Run a Specific Test

To run a specific test file:

```sh
docker run --rm httpd-datadog-tests uv run pytest --bin-path=/httpd/httpd-build/bin/apachectl -v scenarios/test_smoke.py
```

To run a specific test function:

```sh
docker run --rm httpd-datadog-tests uv run pytest --bin-path=/httpd/httpd-build/bin/apachectl -v scenarios/test_smoke.py::test_version_symbol
```

### Command-Line Options

Required options:
- `--bin-path` - Path to apachectl binary (e.g., `/usr/sbin/apachectl`)

Optional options:
- `--module-path` - Path to `mod_datadog.so` (skips auto-build if provided)
- `--log-dir` - Directory for test logs (defaults to temp directory)


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
- Child `<Location>` overrides parent.
- Auto-builds module with `-DHTTPD_DATADOG_ENABLE_RUM=ON` when RUM tests are detected.

### Docker Testing

```sh
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

### Troubleshooting

**RUM build fails:** Check CMake output for missing dependencies (inject-browser-sdk is fetched automatically via CMake FetchContent)

**Tests hang:** Port 8136 in use

```sh
lsof -i :8136
```

**Module issues:**

```sh
ldd /path/to/mod_datadog.so
apachectl -f /path/to/config.conf -t
```
