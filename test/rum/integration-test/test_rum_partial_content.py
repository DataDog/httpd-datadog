"""RUM must preserve partial responses and their byte offsets."""

from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import tempfile

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from upstream import upstream_proxy


HTML = b'<html><head><meta charset="utf-8"></head><body>Hello</body></html>'
CONTENT_RANGE = "bytes 0-65/1000"


class PartialContentUpstream(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, has_range = self.path.strip("/").split("/")
        self.send_response(int(status))
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(HTML)))
        if has_range == "range":
            self.send_header("Content-Range", CONTENT_RANGE)
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.mark.requires_rum
@pytest.mark.parametrize(
    "status, content_range",
    [(206, CONTENT_RANGE), (206, None), (200, CONTENT_RANGE)],
    ids=["partial-with-range", "partial-without-range", "ok-with-range"],
)
def test_rum_preserves_partial_content(
    server: Server, log_dir: str, module_path: str, status: int, content_range: str | None
) -> None:
    conf_path = str(Path(log_dir) / "httpd.conf")
    with ExitStack() as cleanup:
        docroot = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="rum-partial-"))
        proxy = cleanup.enter_context(upstream_proxy(PartialContentUpstream))
        cleanup.callback(server.stop, conf_path)
        configuration = {
            "path": Path(__file__).parent / "conf/rum_content_type.conf",
            "var": {"htdoc_dir": docroot, "proxy_configuration": proxy},
        }
        save_configuration(make_configuration(configuration, log_dir, module_path), conf_path)
        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)

        range_path = "range" if content_range is not None else "no-range"
        response = requests.get(server.make_url(f"/upstream/{status}/{range_path}"), timeout=5)
        assert response.status_code == status
        assert response.headers.get("Content-Type") == "text/html"
        assert response.headers.get("Content-Range") == content_range
        assert response.content == HTML
        assert response.headers.get("Content-Length") == str(len(HTML))
        assert b"DD_RUM" not in response.content
        assert "x-datadog-rum-injected" not in response.headers
