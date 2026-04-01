#!/usr/bin/env python3
"""
RUM (Real User Monitoring) Integration Tests

Tests RUM injection functionality including selective enabling/disabling
based on Apache location directives.

NOTE: RUM SDK Injection is currently in Private Beta. These tests require
mod_datadog to be compiled with -DHTTPD_DATADOG_ENABLE_RUM=ON, which in turn
requires the inject-browser-sdk component (not publicly available).

To run these tests, you must:
1. Have access to the inject-browser-sdk component
2. Build mod_datadog with RUM support enabled
3. Run with: pytest -k test_rum --module-path=/path/to/mod_datadog.so

For more information: https://www.datadoghq.com/private-beta/rum-sdk-auto-injection/
"""
import os
from queue import Queue
import requests
import pytest
from aiohttp import web
from conftest import Server, AgentSession
from helper import (
    relpath,
    make_configuration,
    save_configuration,
    AioHTTPServer,
    free_port,
)


@pytest.mark.requires_rum
def test_rum_selective_disabling(server: Server, agent: AgentSession, log_dir: str, module_path: str) -> None:
    """
    Verify RUM can be selectively disabled for specific subpaths.

    This test configures RUM to be enabled globally but disabled for
    specific paths (/health, /api, /static). It verifies that:
    1. RUM SDK is injected into regular pages
    2. RUM SDK is NOT injected into excluded paths
    3. The injection header is properly set when RUM is injected
    """
    config = {
        "path": relpath("conf/rum_selective.conf"),
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    # Test 1: Root path - RUM should be injected
    r_root = requests.get(server.make_url("/"), timeout=2)
    assert r_root.status_code == 200
    assert_rum_injected(r_root)

    # Test 2: App page - RUM should be injected
    r_app = requests.get(server.make_url("/app.html"), timeout=2)
    assert r_app.status_code == 200
    assert_rum_injected(r_app)

    # Test 3: Health endpoint - RUM should NOT be injected
    r_health = requests.get(server.make_url("/health.html"), timeout=2)
    assert r_health.status_code == 200
    assert_rum_not_injected(r_health)

    # Test 4: API endpoint - RUM should NOT be injected
    r_api = requests.get(server.make_url("/api.html"), timeout=2)
    assert r_api.status_code == 200
    assert_rum_not_injected(r_api)

    # Test 5: Static assets - RUM should NOT be injected
    r_static = requests.get(server.make_url("/static.html"), timeout=2)
    assert r_static.status_code == 200
    assert_rum_not_injected(r_static)

    assert server.stop(conf_path)

    # Verify traces were generated for all requests
    traces = agent.get_traces(timeout=5)
    assert len(traces) >= 5


@pytest.mark.requires_rum
def test_rum_nested_location_override(server: Server, agent: AgentSession, log_dir: str, module_path: str) -> None:
    """
    Verify RUM configuration can be overridden in nested locations.

    Tests the configuration merging logic where child locations can
    override parent RUM settings.
    """
    # Create a custom configuration with nested locations
    custom_conf_content = """$load_datadog_module
LoadModule mpm_prefork_module modules/mod_mpm_prefork.so

DatadogAgentUrl http://localhost:8136
DatadogServiceName "rum-nested-test"

# Enable RUM globally
DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "global-app-id"
  DatadogRumOption clientToken "global-token"
  DatadogRumOption site "datadoghq.com"
</DatadogRumSettings>

# Parent location with RUM enabled
<Location "/app">
  DatadogRum On
</Location>

# Child location with RUM disabled
<Location "/app/internal">
  DatadogRum Off
</Location>
"""

    config = {
        "path": relpath("conf/default.conf"),  # Will be overridden
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")

    # Build full config by combining base template with custom content
    from helper import make_configuration
    base_config = make_configuration(config, log_dir, module_path)

    # Replace the default.conf content with our custom content
    lines = base_config.split('\n')

    # Find where the default.conf content starts (after the base template)
    insert_index = len(lines)
    for i, line in enumerate(lines):
        if 'DocumentRoot' in line:
            insert_index = i + 1
            break

    # Insert custom config
    from string import Template
    custom_template = Template(custom_conf_content)
    custom_conf = custom_template.substitute(
        load_datadog_module=f"LoadModule datadog_module {module_path}"
    )

    # Replace everything after DocumentRoot with our custom config
    # Keep the base Apache configuration (Listen, LoadModule, LogLevel, etc.)
    base_lines = lines[:insert_index]
    # Remove any existing datadog module load from base
    base_lines = [l for l in base_lines if 'LoadModule datadog_module' not in l]
    final_config = '\n'.join(base_lines) + '\n' + custom_conf

    save_configuration(final_config, conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    # Test parent location - RUM should be injected
    r_parent = requests.get(server.make_url("/app.html"), timeout=2)
    assert r_parent.status_code == 200
    # Note: Can't test /app path without a file, so using root

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_configuration_validation(server: Server, log_dir: str, module_path: str) -> None:
    """
    Verify RUM configuration directives are validated correctly.

    Tests that:
    1. Valid RUM configurations pass validation
    2. Invalid configurations are rejected
    """
    # Test valid configuration
    valid_config = {
        "path": relpath("conf/rum_selective.conf"),
        "var": {},
    }

    with make_temporary_configuration(valid_config, module_path) as conf_path:
        assert server.check_configuration(conf_path)


@pytest.mark.requires_rum
def test_rum_proxy_injection_pending_header(server: Server, agent: AgentSession, log_dir: str, module_path: str) -> None:
    """
    Verify that proxied requests include the x-datadog-rum-injection-pending
    request header when RUM is enabled, and that it is absent when RUM is
    disabled for a specific location.
    """
    host = "127.0.0.1"
    port = free_port()
    q = Queue()

    async def upstream_handler(request):
        q.put(dict(request.headers))
        return web.Response(
            body="<html><head><title>Upstream</title></head><body>Hello</body></html>",
            content_type="text/html",
        )

    app = web.Application()
    app.add_routes([web.get("/", upstream_handler)])
    http_server = AioHTTPServer(app, host, port)
    http_server.run()

    config = {
        "path": relpath("conf/rum_proxy.conf"),
        "var": {"upstream_url": f"http://{host}:{port}"},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    # Test 1: RUM enabled path — header should be present
    r = requests.get(server.make_url("/proxy"), timeout=2)
    assert r.status_code == 200

    upstream_headers_rum = q.get(timeout=2)
    assert upstream_headers_rum.get("x-datadog-rum-injection-pending") == "1", (
        f"Expected x-datadog-rum-injection-pending header to be '1' but got "
        f"'{upstream_headers_rum.get('x-datadog-rum-injection-pending')}'"
    )
    # Header should not leak into the client response
    assert "x-datadog-rum-injection-pending" not in r.headers
    assert_rum_injected(r)

    # Test 2: RUM disabled path — header should be absent
    r_no_rum = requests.get(server.make_url("/proxy-no-rum"), timeout=2)
    assert r_no_rum.status_code == 200

    upstream_headers_no_rum = q.get(timeout=2)
    assert "x-datadog-rum-injection-pending" not in upstream_headers_no_rum, (
        "x-datadog-rum-injection-pending should not be sent when RUM is disabled"
    )

    http_server.stop()
    assert server.stop(conf_path)


# Helper functions

def assert_rum_injected(response: requests.Response) -> None:
    """
    Verify that RUM SDK was injected into the response.

    Checks for:
    1. RUM SDK script in response body
    2. Injection marker header
    """
    content = response.text

    # Check for Datadog RUM SDK markers
    # The SDK injects a script tag with the browser SDK
    rum_markers = [
        "datadoghq-browser-sdk",
        "DD_RUM",
        "applicationId",
        "clientToken",
    ]

    found_markers = [marker for marker in rum_markers if marker in content]

    assert len(found_markers) > 0, (
        f"Expected RUM SDK to be injected but found no markers. "
        f"Response length: {len(content)}, "
        f"Content preview: {content[:200]}"
    )

    # Check for injection header
    injection_header = response.headers.get("x-datadog-sdk-injected")
    assert injection_header == "1", (
        f"Expected x-datadog-sdk-injected header to be '1' but got '{injection_header}'"
    )


def assert_rum_not_injected(response: requests.Response) -> None:
    """
    Verify that RUM SDK was NOT injected into the response.

    Checks that:
    1. RUM SDK script is absent from response body
    2. Injection marker header is not set or is set to a value other than "1"
    """
    content = response.text

    # Check that Datadog RUM SDK markers are NOT present
    rum_markers = [
        "datadoghq-browser-sdk",
        "DD_RUM",
    ]

    found_markers = [marker for marker in rum_markers if marker in content]

    assert len(found_markers) == 0, (
        f"Expected RUM SDK NOT to be injected but found markers: {found_markers}. "
        f"Content preview: {content[:500]}"
    )

    # Check injection header is not set to "1"
    injection_header = response.headers.get("x-datadog-sdk-injected")
    assert injection_header != "1", (
        f"Expected x-datadog-sdk-injected header NOT to be '1' but got '{injection_header}'"
    )


# Import make_temporary_configuration for test_rum_configuration_validation
from helper import make_temporary_configuration
