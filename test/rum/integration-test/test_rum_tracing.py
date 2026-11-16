"""Tracing URLs must be injected as an array for Browser SDK v6."""

import json
from pathlib import Path

import pytest
import requests

from helper import make_configuration, save_configuration
from rum_helper import assert_rum_injected


@pytest.mark.requires_rum
@pytest.mark.parametrize(
    "urls",
    [
        ["https://api.example.com"],
        ["https://api.example.com", "https://other.example.com"],
    ],
    ids=["single-url", "multiple-urls"],
)
def test_rum_allowed_tracing_urls_are_an_array(server, log_dir, module_path, urls):
    configuration = make_configuration(
        {"path": "conf/default.conf", "var": {}}, log_dir, module_path
    )
    arguments = " ".join(f'"{url}"' for url in urls)
    configuration += f"""
LoadModule mime_module modules/mod_mime.so
TypesConfig /dev/null
AddType text/html .html

DatadogRum On
<DatadogRumSettings "v6">
  DatadogRumOption applicationId "test-app-id"
  DatadogRumOption clientToken "test-client-token"
  DatadogRumOption site "datadoghq.com"
  DatadogRumOption service "review-service"
  DatadogRumOption sessionSampleRate "100"
  DatadogRumOption allowedTracingUrls {arguments}
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
        assert config["service"] == "review-service"
        assert isinstance(config["allowedTracingUrls"], list)
        assert config["allowedTracingUrls"] == urls
    finally:
        assert server.stop(conf_path)
