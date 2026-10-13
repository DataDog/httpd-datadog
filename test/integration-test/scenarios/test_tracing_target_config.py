"""Redirects and SSI subrequests must use the target's tracing config."""

from pathlib import Path
import tempfile

import pytest
import requests

from conftest import Server
from helper import free_port, make_configuration, save_configuration


@pytest.mark.ci
@pytest.mark.parametrize("kind", ["redirect", "subrequest"])
@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "tagged"])
def test_tracing_uses_target_config(server, agent, log_dir, module_path, kind, enabled):
    server = Server(server.host, free_port(), server._proc, server._conf)
    conf_path = str(Path(log_dir) / "httpd.conf")
    with tempfile.TemporaryDirectory(prefix="tracing-target-") as document_root:
        root = Path(document_root)
        root.chmod(0o755)
        (root / "target.html").write_text("target body")
        (root / "include.shtml").write_text('<!--#include virtual="/target.html" -->')
        configuration = make_configuration(
            {
                "path": "conf/default.conf",
                "var": {"htdoc_dir": document_root, "port": server.port},
            },
            log_dir, module_path,
        )
        configuration += f"""
LoadModule include_module modules/mod_include.so
LoadModule mime_module modules/mod_mime.so
TypesConfig /dev/null
AddType text/html .html .shtml
AddOutputFilter INCLUDES .shtml
DatadogAddTag scope source
<Directory "{document_root}">
  Require all granted
  Options +Includes
</Directory>
<Location "/missing">
  ErrorDocument 404 /target.html
</Location>
<Location "/target.html">
  DatadogTracing {"On" if enabled else "Off"}
  DatadogAddTag scope target
</Location>
"""
        save_configuration(configuration, conf_path)
        assert server.check_configuration(conf_path)
        try:
            assert server.load_configuration(conf_path)
            path = "/missing" if kind == "redirect" else "/include.shtml"
            response = requests.get(server.make_url(path), timeout=5)
            assert response.status_code == (404 if kind == "redirect" else 200)
            assert response.content == b"target body"
        finally:
            server.stop(conf_path)

        spans = [span for trace in agent.get_traces(timeout=5) for span in trace]
        roots = [span for span in spans if span["resource"].split()[1] == path]
        targets = [
            span for span in spans if span["resource"].split()[1] == "/target.html"
        ]
        assert len(roots) == 1, spans
        assert roots[0]["meta"]["scope"] == "source"
        if enabled:
            assert len(targets) == 1, spans
            assert targets[0]["meta"]["scope"] == "target"
            assert targets[0]["parent_id"] == roots[0]["span_id"]
        else:
            assert targets == [], spans
