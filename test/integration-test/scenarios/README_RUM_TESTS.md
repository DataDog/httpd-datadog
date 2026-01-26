# RUM Selective Disabling Tests

This document describes the integration tests for RUM (Real User Monitoring) selective disabling functionality.

## Overview

The RUM module supports path-based configuration using Apache's `<Location>` and `<Directory>` directives. This allows RUM to be enabled globally but selectively disabled for specific paths like health checks, API endpoints, or static assets.

## Test Files

### Configuration
- **`conf/rum_selective.conf`** - Apache configuration with RUM enabled globally but disabled for `/health`, `/api`, and `/static` paths

### Test HTML Files
- **`htdocs/app.html`** - Regular application page (RUM should be injected)
- **`htdocs/health.html`** - Health check page (RUM should NOT be injected)
- **`htdocs/api.html`** - API endpoint page (RUM should NOT be injected)
- **`htdocs/static.html`** - Static asset page (RUM should NOT be injected)

### Test Script
- **`test_rum.py`** - pytest test suite with three test cases

## Test Cases

### 1. `test_rum_selective_disabling`

**Purpose**: Verify RUM can be selectively disabled for specific subpaths.

**Test Flow**:
1. Load configuration with RUM enabled globally
2. Make HTTP requests to different paths:
   - `/` (root) - Should have RUM injected
   - `/app.html` - Should have RUM injected
   - `/health.html` - Should NOT have RUM injected
   - `/api.html` - Should NOT have RUM injected
   - `/static.html` - Should NOT have RUM injected
3. Verify RUM injection status for each path

**Verification**:
- Checks response body for RUM SDK markers:
  - `datadoghq-browser-sdk`
  - `DD_RUM`
  - `applicationId`
  - `clientToken`
- Checks `x-datadog-sdk-injected` header (should be "1" when injected)

### 2. `test_rum_nested_location_override`

**Purpose**: Verify RUM configuration can be overridden in nested locations.

**Test Flow**:
1. Create configuration with nested `<Location>` blocks
2. Parent location `/app` has RUM enabled
3. Child location `/app/internal` has RUM disabled
4. Verify child can override parent settings

**Configuration Merging Logic**:
```cpp
// From rum/config.cpp:179-190
void merge_directory_configuration(Directory& out, const Directory& parent,
                                   const Directory& child) {
  out.enabled = child.enabled || parent.enabled;
  // Child settings override parent
}
```

### 3. `test_rum_configuration_validation`

**Purpose**: Verify RUM configuration directives are validated correctly.

**Test Flow**:
1. Test valid RUM configurations pass Apache's configuration validation
2. Ensures configuration syntax is correct

## Configuration Example

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

# Disable RUM for health checks
<Location "/health">
  DatadogRum Off
</Location>

# Disable RUM for API endpoints
<Location "/api">
  DatadogRum Off
</Location>
```

## Running the Tests

### Prerequisites
- Apache httpd with mod_datadog compiled
- Python 3.x with pytest installed
- dd-apm-test-agent running on localhost:8136

### Run All RUM Tests
```bash
cd test/integration-test
pytest scenarios/test_rum.py -v
```

### Run Specific Test
```bash
pytest scenarios/test_rum.py::test_rum_selective_disabling -v
```

### Run with Debug Output
```bash
pytest scenarios/test_rum.py -v -s
```

## Implementation Details

### RUM Filter Decision Logic

The RUM filter (mod_datadog/src/rum/filter.cpp) checks several conditions before injecting:

1. **RUM Enabled**: Checks `dir_conf->rum.enabled` for the request path
2. **Content-Type**: Only injects into `text/html` responses
3. **Content-Encoding**: Skips compressed content
4. **Already Injected**: Checks `x-datadog-sdk-injected` header to prevent double injection

```cpp
// From rum/filter.cpp:91-119
int rum_output_filter(ap_filter_t* f, apr_bucket_brigade* bb) {
  auto* dir_conf = static_cast<Directory*>(
      ap_get_module_config(r->per_dir_config, &datadog_module));

  if (!dir_conf->rum.enabled || dir_conf->rum.snippet == nullptr) {
    return ap_pass_brigade(f->next, bb);  // Skip injection
  }

  if (!should_inject(ctx, *r, dir_conf->rum)) {
    return ap_pass_brigade(f->next, bb);
  }

  // Perform injection...
}
```

### Telemetry Metrics

RUM tracks injection decisions with telemetry:
- `injection.succeed` - Successful injections
- `injection.skipped` - Skipped injections (with reason tags)
- `injection.failed` - Failed injections

Tags include: `integration_name:httpd`, `application_id:*`, `remote_config_used:*`

## Expected Test Results

When all tests pass, you should see:
```
test_rum.py::test_rum_selective_disabling PASSED
test_rum.py::test_rum_nested_location_override PASSED
test_rum.py::test_rum_configuration_validation PASSED
```

## Troubleshooting

### RUM Not Injecting
- Check Apache error logs for configuration errors
- Verify `DatadogRum On` is set
- Ensure RUM settings include mandatory fields: `applicationId`, `clientToken`, `site`
- Verify Content-Type is `text/html`
- Check response is not compressed

### RUM Injecting When It Shouldn't
- Verify `<Location>` directives are correctly ordered
- Check Apache's location matching rules
- Review per-directory configuration merging logic

### Configuration Validation Fails
- Check Apache syntax with `apachectl configtest`
- Review DatadogRumOption syntax
- Ensure all DatadogRumSettings blocks are properly closed

## Related Files

- `mod_datadog/src/rum/config.h` - RUM configuration structures
- `mod_datadog/src/rum/config.cpp` - Configuration parsing and merging
- `mod_datadog/src/rum/filter.h` - RUM filter declarations
- `mod_datadog/src/rum/filter.cpp` - RUM injection logic
- `mod_datadog/src/rum/telemetry.cpp` - RUM telemetry metrics
- `doc/configuration.md` - RUM configuration documentation
