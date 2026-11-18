"""Each DatadogRumOption argument is one value of the injected RUM options."""

import json
from pathlib import Path

import pytest
import requests

from helper import make_configuration, save_configuration
from rum_helper import assert_rum_injected


@pytest.mark.requires_rum
@pytest.mark.parametrize(
    "option, arguments, expected",
    [
        ("allowedTracingUrls", ["https://api.example.com"], ["https://api.example.com"]),
        (
            "allowedTracingUrls",
            ["https://api.example.com", "https://other.example.com"],
            ["https://api.example.com", "https://other.example.com"],
        ),
        ("allowedTracingUrls", ["https://api.example.com/a,b"], ["https://api.example.com/a,b"]),
        ("excludedActivityUrls", ["https://example.com/poll"], ["https://example.com/poll"]),
        ("env", ["a,b"], "a,b"),
    ],
    ids=["single-url", "multiple-urls", "url-with-comma", "excluded-activity-url", "scalar-with-comma"],
)
def test_rum_option_values(server, log_dir, module_path, option, arguments, expected):
    configuration = make_configuration(
        {"path": "conf/default.conf", "var": {}}, log_dir, module_path
    )
    values = " ".join(f'"{argument}"' for argument in arguments)
    # The Browser SDK needs a service when allowedTracingUrls is set.
    configuration += f"""
LoadModule mime_module modules/mod_mime.so
TypesConfig /dev/null
AddType text/html .html

DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "test-app-id"
  DatadogRumOption clientToken "test-client-token"
  DatadogRumOption service "test-service"
  DatadogRumOption {option} {values}
</DatadogRumSettings>
"""
    conf_path = str(Path(log_dir) / "httpd.conf")
    save_configuration(configuration, conf_path)
    assert server.check_configuration(conf_path)
    try:
        assert server.load_configuration(conf_path)
        response = requests.get(server.make_url("/index.html"), timeout=2)
        assert response.status_code == 200
        assert_rum_injected(response)

        _, marker, initialization = response.text.partition("window.DD_RUM.init(")
        assert marker, response.text
        config, _ = json.JSONDecoder().raw_decode(initialization.lstrip())
        assert config[option] == expected
    finally:
        assert server.stop(conf_path)
