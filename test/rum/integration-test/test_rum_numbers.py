"""Malformed RUM numbers must produce config errors instead of aborting Apache."""

from pathlib import Path

import pytest

from helper import make_configuration, save_configuration


pytestmark = pytest.mark.requires_rum


def check_settings(server, log_dir, module_path, version, option, value):
    configuration = make_configuration(
        {"path": "conf/default.conf", "var": {}}, log_dir, module_path
    )
    configuration += f"""
DatadogRum On
<DatadogRumSettings "{version}">
  DatadogRumOption applicationId "test-app"
  DatadogRumOption clientToken "test-token"
  DatadogRumOption {option} "{value}"
</DatadogRumSettings>
"""
    conf_path = str(Path(log_dir) / "httpd.conf")
    save_configuration(configuration, conf_path)
    return server._proc.run(f"-f {conf_path} -t")


@pytest.mark.parametrize("option", ["sessionSampleRate", "sessionReplaySampleRate"])
@pytest.mark.parametrize(
    "value", ["invalid", "1e9999", "10junk", "10 ", "nan", "inf"],
    ids=["invalid", "overflow", "trailing-text", "trailing-space", "nan", "inf"],
)
def test_rum_invalid_rate_is_config_error(server, log_dir, module_path, option, value):
    result = check_settings(server, log_dir, module_path, "v6", option, value)
    assert result.returncode == 1, result.stderr
    assert b"Syntax error" in result.stderr


@pytest.mark.parametrize("version", ["v99999999999999999999", "w6"])
def test_rum_invalid_version_is_config_error(server, log_dir, module_path, version):
    result = check_settings(
        server, log_dir, module_path, version, "sessionSampleRate", "100"
    )
    assert result.returncode == 1, result.stderr
    assert b"Syntax error" in result.stderr


@pytest.mark.parametrize("option", ["sessionSampleRate", "sessionReplaySampleRate"])
@pytest.mark.parametrize("value", ["0", "10.5", "100", "1e1"])
def test_rum_valid_rates_are_accepted(server, log_dir, module_path, option, value):
    result = check_settings(server, log_dir, module_path, "v6", option, value)
    assert result.returncode == 0, result.stderr
