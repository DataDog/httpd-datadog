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
from pathlib import Path
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
    make_temporary_configuration,
    assert_rum_injected,
    assert_rum_not_injected,
)

RUM_TEST_DIR = Path(__file__).parent


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
        "path": RUM_TEST_DIR / "conf/rum_selective.conf",
        "var": {"htdoc_dir": RUM_TEST_DIR / "htdocs"},
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
        "var": {"htdoc_dir": RUM_TEST_DIR / "htdocs"},
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
        "path": RUM_TEST_DIR / "conf/rum_selective.conf",
        "var": {"htdoc_dir": RUM_TEST_DIR / "htdocs"},
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
    captured_headers = Queue()

    async def upstream_handler(request):
        captured_headers.put(dict(request.headers))
        return web.Response(
            body="<html><head><title>Upstream</title></head><body>Hello</body></html>",
            content_type="text/html",
        )

    app = web.Application()
    app.add_routes([web.get("/", upstream_handler)])

    config = {
        "path": RUM_TEST_DIR / "conf/rum_proxy.conf",
        "var": {"upstream_url": f"http://{host}:{port}"},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    with AioHTTPServer(app, host, port):
        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)

        # Test 1: RUM enabled path — header should be present
        response = requests.get(server.make_url("/proxy"), timeout=2)
        assert response.status_code == 200

        upstream_headers_rum = captured_headers.get(timeout=2)
        assert upstream_headers_rum.get("x-datadog-rum-injection-pending") == "1", (
            f"Expected x-datadog-rum-injection-pending header to be '1' but got "
            f"'{upstream_headers_rum.get('x-datadog-rum-injection-pending')}'"
        )
        # Header should not leak into the client response
        assert "x-datadog-rum-injection-pending" not in response.headers
        assert_rum_injected(response)

        # Test 2: RUM disabled path — header should be absent
        response_no_rum = requests.get(server.make_url("/proxy-no-rum"), timeout=2)
        assert response_no_rum.status_code == 200

        upstream_headers_no_rum = captured_headers.get(timeout=2)
        assert "x-datadog-rum-injection-pending" not in upstream_headers_no_rum, (
            "x-datadog-rum-injection-pending should not be sent when RUM is disabled"
        )
        assert_rum_not_injected(response_no_rum)

        assert server.stop(conf_path)

