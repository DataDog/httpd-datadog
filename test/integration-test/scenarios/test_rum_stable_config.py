#!/usr/bin/env python3
"""
RUM stable-configuration integration tests.

Stable configuration is the Agent-managed `application_monitoring.yaml`. The RUM
SDK reads it directly, so mod_datadog can inject RUM with nothing in httpd.conf
at all -- which is what SSI/auto-injection relies on, since the injector cannot
edit a user's configuration.

Precedence under test:

    <DatadogRumSettings> block  >  application_monitoring.yaml  >  nothing
    DatadogRum directive        >  DD_RUM_ENABLED  >  "on iff stable config gave a snippet"

Same build requirements as test_rum.py: -DHTTPD_DATADOG_ENABLE_RUM=ON.
"""
import os
from pathlib import Path

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from test_rum import assert_rum_injected, assert_rum_not_injected

# Where the SDK looks for local stable configuration on Linux. Not
# configurable: it is a compile-time constant in libdd-library-config
# (Configurator::LOCAL_STABLE_CONFIGURATION_PATH).
STABLE_CONFIG_PATH = Path("/etc/datadog-agent/application_monitoring.yaml")

STABLE_CONFIG_APP_ID = "stable-config-app-id"
OVERLAY_APP_ID = "directive-overlay-app-id"


def stable_config_yaml(application_id: str = STABLE_CONFIG_APP_ID) -> str:
    return f"""apm_configuration_default:
  DD_RUM_MAJOR_VERSION: 6
  DD_RUM_APPLICATION_ID: "{application_id}"
  DD_RUM_CLIENT_TOKEN: "stable-config-client-token"
  DD_RUM_SITE: "datadoghq.com"
"""


@pytest.fixture
def stable_config(request):
    """
    Installs application_monitoring.yaml for one test and restores whatever was
    there before.

    The path is fixed and absolute, so this needs write access to
    /etc/datadog-agent. That holds in the CI image (root) but not necessarily on
    a workstation, hence the skip rather than a failure.
    """
    content = getattr(request, "param", stable_config_yaml())

    try:
        STABLE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        pytest.skip(f"cannot create {STABLE_CONFIG_PATH.parent}; needs root")

    previous = STABLE_CONFIG_PATH.read_bytes() if STABLE_CONFIG_PATH.exists() else None
    try:
        STABLE_CONFIG_PATH.write_text(content)
    except PermissionError:
        pytest.skip(f"cannot write {STABLE_CONFIG_PATH}; needs root")

    try:
        yield content
    finally:
        if previous is None:
            STABLE_CONFIG_PATH.unlink(missing_ok=True)
        else:
            STABLE_CONFIG_PATH.write_bytes(previous)


@pytest.fixture
def no_stable_config():
    """Guarantees no stable configuration is visible, restoring any that was."""
    previous = STABLE_CONFIG_PATH.read_bytes() if STABLE_CONFIG_PATH.exists() else None
    if previous is not None:
        try:
            STABLE_CONFIG_PATH.unlink()
        except PermissionError:
            pytest.skip(f"cannot remove {STABLE_CONFIG_PATH}; needs root")
    try:
        yield
    finally:
        if previous is not None:
            STABLE_CONFIG_PATH.write_bytes(previous)


# Prepended to every test body. Mirrors conf/default.conf; $load_datadog_module
# is expanded by make_configuration, so the fragment must go through it rather
# than being written out directly.
CONF_PREAMBLE = """$load_datadog_module
LoadModule mpm_prefork_module modules/mod_mpm_prefork.so

DatadogAgentUrl http://localhost:8136
"""


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
    server: Server, log_dir: str, module_path: str, stable_config: str
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
    server: Server, log_dir: str, module_path: str, stable_config: str
) -> None:
    """
    A <DatadogRumSettings> block is an overlay on stable configuration, and wins
    on the keys it sets. This is the behaviour change from
    snippet_create_from_json: previously the block ignored stable config
    entirely.
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
    server: Server, log_dir: str, module_path: str, stable_config: str
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
    stable_config: str,
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
