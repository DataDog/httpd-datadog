#!/usr/bin/env python3
"""
RUM stable-configuration integration tests.

Stable configuration is the Agent-managed `application_monitoring.yaml`. The RUM
SDK reads it directly, so mod_datadog can inject RUM with nothing in httpd.conf
at all -- which is what SSI/auto-injection relies on, since the injector cannot
edit a user's configuration.

Precedence under test:

    <DatadogRumSettings> block  >  application_monitoring.yaml  >  nothing
    DatadogRum directive  >  DD_RUM_ENABLED in the environment
                          >  DD_RUM_ENABLED in stable configuration
                          >  "on iff stable config gave a snippet"

Exception: `DD_RUM_ENABLED: false` in stable configuration is a kill switch.
It wins over both the directive and the environment.

Same build requirements as test_rum.py: -DHTTPD_DATADOG_ENABLE_RUM=ON.
"""
import os
import time
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Iterator, Optional

import pytest
import requests
from aiohttp import web

from conftest import Server
from helper import (
    AioHTTPServer,
    assert_rum_injected,
    assert_rum_not_injected,
    free_port,
    make_configuration,
    relpath,
    save_configuration,
)

# Where the SDK looks for local stable configuration on Linux. Not
# configurable: it is a compile-time constant in libdd-library-config
# (Configurator::LOCAL_STABLE_CONFIGURATION_PATH).
STABLE_CONFIG_PATH = Path("/etc/datadog-agent/application_monitoring.yaml")

STABLE_CONFIG_APP_ID = "stable-config-app-id"
OVERLAY_APP_ID = "directive-overlay-app-id"


STABLE_CONFIG_YAML = f"""apm_configuration_default:
  DD_RUM_MAJOR_VERSION: 6
  DD_RUM_APPLICATION_ID: "{STABLE_CONFIG_APP_ID}"
  DD_RUM_CLIENT_TOKEN: "stable-config-client-token"
  DD_RUM_SITE: "datadoghq.com"
"""

# Same RUM data keys, plus the kill switch. Injection must stop even though the
# data keys alone would be enough to build a snippet.
STABLE_CONFIG_YAML_DISABLED = f"""apm_configuration_default:
  DD_RUM_ENABLED: false
  DD_RUM_MAJOR_VERSION: 6
  DD_RUM_APPLICATION_ID: "{STABLE_CONFIG_APP_ID}"
  DD_RUM_CLIENT_TOKEN: "stable-config-client-token"
  DD_RUM_SITE: "datadoghq.com"
"""

# Turns RUM on but lacks the applicationId and clientToken, so stable
# configuration alone cannot build a snippet.
STABLE_CONFIG_YAML_ENABLED_PARTIAL = """apm_configuration_default:
  DD_RUM_ENABLED: true
  DD_RUM_MAJOR_VERSION: 6
  DD_RUM_SITE: "datadoghq.com"
"""

# Invalid stable configuration: a YAML read error, and a bad value.
STABLE_CONFIG_YAML_BROKEN = "apm_configuration_default: [\n"

STABLE_CONFIG_YAML_INVALID_VALUE = STABLE_CONFIG_YAML + "  DD_RUM_SESSION_SAMPLE_RATE: abc\n"

STABLE_CONFIG_YAML_DISABLED_INVALID_VALUE = (
    STABLE_CONFIG_YAML_DISABLED + "  DD_RUM_SESSION_SAMPLE_RATE: abc\n"
)


@contextmanager
def installed_stable_config(content: Optional[str]) -> Iterator[None]:
    """
    Puts application_monitoring.yaml in the state `content` describes -- written
    out, or absent when None -- and restores whatever was there before.

    The path is fixed and absolute, so this needs write access to
    /etc/datadog-agent. That holds in the CI image (root) but not necessarily on
    a workstation, hence the skips rather than failures.
    """
    previous = STABLE_CONFIG_PATH.read_bytes() if STABLE_CONFIG_PATH.exists() else None
    try:
        if content is None:
            STABLE_CONFIG_PATH.unlink(missing_ok=True)
        else:
            STABLE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            STABLE_CONFIG_PATH.write_text(content)
    except PermissionError:
        pytest.skip(f"cannot modify {STABLE_CONFIG_PATH}; needs root")

    try:
        yield
    finally:
        if previous is None:
            STABLE_CONFIG_PATH.unlink(missing_ok=True)
        else:
            STABLE_CONFIG_PATH.write_bytes(previous)


@pytest.fixture
def stable_config() -> Iterator[None]:
    """Installs application_monitoring.yaml for the duration of one test."""
    with installed_stable_config(STABLE_CONFIG_YAML):
        yield


@pytest.fixture
def stable_config_disabled() -> Iterator[None]:
    """Stable configuration carrying RUM keys *and* `DD_RUM_ENABLED: false`."""
    with installed_stable_config(STABLE_CONFIG_YAML_DISABLED):
        yield


@pytest.fixture
def no_stable_config() -> Iterator[None]:
    """Guarantees no stable configuration is visible, restoring any that was."""
    with installed_stable_config(None):
        yield


# Prepended to every test body. $load_datadog_module is expanded by
# make_configuration, so the fragment must go through it rather than being
# written out directly.
CONF_PREAMBLE = (
    Path(relpath("conf/default.conf")).read_text()
    + """
LoadModule mime_module modules/mod_mime.so
TypesConfig /dev/null
AddType text/html .html
"""
)


def start(server: Server, log_dir: str, module_path: str, conf_body: str) -> str:
    """
    Starts httpd on a configuration whose RUM section is exactly `conf_body`.

    Each test needs a different RUM section, and the existing fixtures take a
    path to a fragment rather than inline text, so write the fragment out and
    hand make_configuration the path -- that also gets $load_datadog_module
    substituted for free.
    """
    fragment_path = os.path.join(log_dir, "rum_stable_config.conf")
    save_configuration(CONF_PREAMBLE + conf_body, fragment_path)

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(
        make_configuration({"path": fragment_path, "var": {}}, log_dir, module_path),
        conf_path,
    )

    assert server.check_configuration(conf_path), "httpd rejected the configuration"
    assert server.load_configuration(conf_path), "httpd failed to start"
    return conf_path


@pytest.mark.requires_rum
def test_rum_injects_from_stable_config_alone(
    server: Server, log_dir: str, module_path: str, stable_config: None
) -> None:
    """
    The zero-configuration case SSI depends on: application_monitoring.yaml is
    present, httpd.conf mentions no RUM directive whatsoever, and RUM is still
    injected.
    """
    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_injected(response)
    assert STABLE_CONFIG_APP_ID in response.text, (
        "expected the applicationId from stable configuration in the snippet"
    )

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_directive_overlays_stable_config(
    server: Server, log_dir: str, module_path: str, stable_config: None
) -> None:
    """
    A <DatadogRumSettings> block is an overlay on stable configuration, and wins
    on the keys it sets.
    """
    body = f"""DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "{OVERLAY_APP_ID}"
  DatadogRumOption clientToken "overlay-client-token"
  DatadogRumOption site "datadoghq.com"
</DatadogRumSettings>
"""
    conf_path = start(server, log_dir, module_path, body)

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_injected(response)
    assert OVERLAY_APP_ID in response.text, "directive applicationId should win"
    assert STABLE_CONFIG_APP_ID not in response.text, (
        "stable-config applicationId should have been overridden"
    )

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_directive_off_overrides_stable_config(
    server: Server, log_dir: str, module_path: str, stable_config: None
) -> None:
    """An explicit `DatadogRum Off` beats stable configuration turning RUM on."""
    conf_path = start(server, log_dir, module_path, "DatadogRum Off\n")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_stable_config_disabled_by_env(
    server: Server,
    log_dir: str,
    module_path: str,
    stable_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    DD_RUM_ENABLED=false suppresses the stable-config default. httpd inherits the
    environment from pytest, so setting it here reaches the server process.
    """
    monkeypatch.setenv("DD_RUM_ENABLED", "false")

    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_stable_config_can_turn_rum_off(
    server: Server, log_dir: str, module_path: str, stable_config_disabled: None
) -> None:
    """
    `DD_RUM_ENABLED: false` in application_monitoring.yaml must switch injection
    off, with the RUM data keys still present beside it. This is the
    fleet-managed kill switch.
    """
    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_directive_does_not_override_stable_config_disable(
    server: Server, log_dir: str, module_path: str, stable_config_disabled: None
) -> None:
    """`DatadogRum On` cannot override `DD_RUM_ENABLED: false` from stable config."""
    conf_path = start(server, log_dir, module_path, "DatadogRum On\n")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_settings_block_does_not_override_stable_config_disable(
    server: Server, log_dir: str, module_path: str, stable_config_disabled: None
) -> None:
    """A <DatadogRumSettings> block cannot override `DD_RUM_ENABLED: false` either."""
    body = f"""DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "{OVERLAY_APP_ID}"
  DatadogRumOption clientToken "overlay-client-token"
  DatadogRumOption site "datadoghq.com"
</DatadogRumSettings>
"""
    conf_path = start(server, log_dir, module_path, body)

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
@pytest.mark.parametrize(
    "stable_config_yaml, expect_injected",
    [
        (STABLE_CONFIG_YAML_BROKEN, True),
        (STABLE_CONFIG_YAML_INVALID_VALUE, True),
        (STABLE_CONFIG_YAML_DISABLED_INVALID_VALUE, False),
    ],
    ids=["broken_yaml", "invalid_value", "kill_switch_with_invalid_value"],
)
def test_rum_settings_block_ignores_invalid_stable_config(
    server: Server,
    log_dir: str,
    module_path: str,
    stable_config_yaml: str,
    expect_injected: bool,
) -> None:
    """
    Invalid stable configuration must not stop httpd: a complete
    <DatadogRumSettings> block then uses only its own options. The kill switch
    still wins when the other stable-config values are invalid.
    """
    body = f"""DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "{OVERLAY_APP_ID}"
  DatadogRumOption clientToken "overlay-client-token"
  DatadogRumOption site "datadoghq.com"
</DatadogRumSettings>
"""
    with installed_stable_config(stable_config_yaml):
        conf_path = start(server, log_dir, module_path, body)

        response = requests.get(server.make_url("/"), timeout=2)
        assert response.status_code == 200
        if expect_injected:
            assert_rum_injected(response)
            assert OVERLAY_APP_ID in response.text
        else:
            assert_rum_not_injected(response)

        assert server.stop(conf_path)


@pytest.mark.requires_rum
@pytest.mark.parametrize(
    "with_settings_block", [True, False], ids=["settings_block", "no_settings_block"]
)
def test_rum_stable_config_enable_with_partial_settings(
    server: Server, log_dir: str, module_path: str, with_settings_block: bool
) -> None:
    """
    `DD_RUM_ENABLED: true` in stable configuration turns RUM on without a
    DatadogRum directive, even when a <DatadogRumSettings> block supplies the
    keys stable configuration lacks. Without a block, there is nothing to
    inject, and httpd must still start.
    """
    body = ""
    if with_settings_block:
        body = f"""<DatadogRumSettings "v6">
  DatadogRumOption applicationId "{OVERLAY_APP_ID}"
  DatadogRumOption clientToken "overlay-client-token"
</DatadogRumSettings>
"""
    with installed_stable_config(STABLE_CONFIG_YAML_ENABLED_PARTIAL):
        conf_path = start(server, log_dir, module_path, body)

        response = requests.get(server.make_url("/"), timeout=2)
        assert response.status_code == 200
        if with_settings_block:
            assert_rum_injected(response)
            assert OVERLAY_APP_ID in response.text
        else:
            assert_rum_not_injected(response)

        assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_graceful_restart_rereads_stable_config(
    server: Server, log_dir: str, module_path: str, stable_config: None
) -> None:
    """A graceful restart applies a stable-config change without a full restart."""
    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert_rum_injected(response)

    STABLE_CONFIG_PATH.write_text(STABLE_CONFIG_YAML_DISABLED)
    assert server.graceful(conf_path)

    # Old children keep serving until they finish their current connection.
    deadline = time.monotonic() + 5
    while True:
        response = requests.get(server.make_url("/"), timeout=2)
        if response.headers.get("x-datadog-sdk-injected") != "1":
            break
        assert time.monotonic() < deadline, "graceful restart did not disable RUM"
        time.sleep(0.2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_env_does_not_override_stable_config_disable(
    server: Server,
    log_dir: str,
    module_path: str,
    stable_config_disabled: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `DD_RUM_ENABLED=true` in the environment cannot override
    `DD_RUM_ENABLED: false` in stable configuration.
    """
    monkeypatch.setenv("DD_RUM_ENABLED", "true")

    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_off_without_stable_config(
    server: Server, log_dir: str, module_path: str, no_stable_config: None
) -> None:
    """
    Regression guard on the default: with no stable configuration and no
    directives, RUM must stay off. A missing application_monitoring.yaml is the
    ordinary case and must not be treated as an error either -- httpd has to
    start cleanly.
    """
    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
def test_rum_enabled_env_without_snippet_still_starts(
    server: Server,
    log_dir: str,
    module_path: str,
    no_stable_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    DD_RUM_ENABLED=true with nothing to inject is a warning, not a fatal error:
    httpd must still start and serve, just without RUM.
    """
    monkeypatch.setenv("DD_RUM_ENABLED", "true")

    conf_path = start(server, log_dir, module_path, "")

    response = requests.get(server.make_url("/"), timeout=2)
    assert response.status_code == 200
    assert_rum_not_injected(response)

    assert server.stop(conf_path)


@pytest.mark.requires_rum
@pytest.mark.parametrize(
    "stable_config_yaml, expect_pending",
    [(STABLE_CONFIG_YAML, True), (STABLE_CONFIG_YAML_DISABLED, False)],
    ids=["enabled", "disabled"],
)
def test_rum_proxy_injection_pending_header_from_stable_config(
    server: Server,
    log_dir: str,
    module_path: str,
    stable_config_yaml: str,
    expect_pending: bool,
) -> None:
    """
    x-datadog-rum-injection-pending follows the resolved configuration: it is
    sent upstream when stable configuration alone enables RUM, and not sent
    when stable configuration disables it.
    """
    host = "127.0.0.1"
    port = free_port()
    captured_headers: Queue = Queue()

    async def upstream_handler(request):
        captured_headers.put(dict(request.headers))
        return web.Response(
            body="<html><head><title>Upstream</title></head><body>Hello</body></html>",
            content_type="text/html",
        )

    app = web.Application()
    app.add_routes([web.get("/", upstream_handler)])

    body = f"""LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
ProxyPass "/proxy" "http://{host}:{port}"
"""
    with installed_stable_config(stable_config_yaml), AioHTTPServer(app, host, port):
        conf_path = start(server, log_dir, module_path, body)

        response = requests.get(server.make_url("/proxy"), timeout=2)
        assert response.status_code == 200

        upstream_headers = captured_headers.get(timeout=2)
        if expect_pending:
            assert upstream_headers.get("x-datadog-rum-injection-pending") == "1"
            assert_rum_injected(response)
        else:
            assert "x-datadog-rum-injection-pending" not in upstream_headers
            assert_rum_not_injected(response)

        assert server.stop(conf_path)
