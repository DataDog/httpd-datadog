"""CGI response markers must prevent a second RUM injection."""

from pathlib import Path
import tempfile

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from rum_helper import assert_rum_injected


@pytest.mark.requires_rum
def test_rum_skips_already_injected_cgi(
    server: Server, log_dir: str, module_path: str
) -> None:
    conf_path = str(Path(log_dir) / "httpd.conf")
    with tempfile.TemporaryDirectory(prefix="rum-cgi-") as docroot:
        root = Path(docroot)
        root.chmod(0o755)
        script = root / "page.cgi"
        script.write_text(
            "#!/bin/sh\n"
            "printf 'Content-Type: text/html\\r\\n'\n"
            'cat "$(dirname "$0")/response"\n'
        )
        script.chmod(0o755)
        body = b"<html><head><title>CGI</title></head><body>Hello</body></html>"
        response_file = root / "response"
        response_file.write_bytes(b"\r\n" + body)
        response_file.chmod(0o644)
        config = {
            "path": Path(__file__).parent / "conf/rum_cgi.conf",
            "var": {"htdoc_dir": docroot, "script_socket": str(root / "cgisock")},
        }
        save_configuration(make_configuration(config, log_dir, module_path), conf_path)
        assert server.check_configuration(conf_path)
        try:
            assert server.load_configuration(conf_path)
            first = requests.get(server.make_url("/cgi/page.cgi"), timeout=5)
            assert first.status_code == 200
            assert_rum_injected(first)
            assert first.content.count(b"window.DD_RUM.init") == 1

            response_file.write_bytes(
                b"x-datadog-rum-injected: 1\r\n\r\n" + first.content
            )
            second = requests.get(server.make_url("/cgi/page.cgi"), timeout=5)
            assert second.status_code == 200
            assert second.content.count(b"window.DD_RUM.init") == 1
            assert second.content == first.content
            assert second.headers.get("x-datadog-rum-injected") == "1"
        finally:
            assert server.stop(conf_path)
