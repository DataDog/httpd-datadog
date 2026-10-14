"""RUM must handle an HTML body split at any point across buckets."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
import time

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration

# Each page is sent in two writes, split inside a possible `</head>` tag.
PAGES = {
    "/head": [b"<html><head><title>t</title></he", b"ad><body>ok</body></html>"],
    "/no-head": [b"<html><body><", b"div>ok</div></body></html>"],
    "/held-at-end": [b"<html><body>ok</body></html>", b"</hea"],
}


@pytest.mark.requires_rum
def test_rum_split_body(server: Server, log_dir: str, module_path: str) -> None:
    conf_path = str(Path(log_dir) / "httpd.conf")
    with split_upstream() as upstream_url:
        config = {"path": "conf/rum_proxy.conf", "var": {"upstream_url": upstream_url}}
        save_configuration(make_configuration(config, log_dir, module_path), conf_path)
        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)
        try:
            assert_injected_once(server)
            assert_unchanged(server, "/no-head")
            assert_unchanged(server, "/held-at-end")
        finally:
            server.stop(conf_path)


def assert_injected_once(server: Server) -> None:
    response = requests.get(server.make_url("/proxy/head"), timeout=5)
    assert response.status_code == 200
    pattern = (
        re.escape(b"<html><head><title>t</title>")
        + rb"\s*<script>.*DD_RUM.*</script>\s*"
        + re.escape(b"</head><body>ok</body></html>")
    )
    assert re.fullmatch(pattern, response.content, re.DOTALL), response.content


def assert_unchanged(server: Server, path: str) -> None:
    response = requests.get(server.make_url(f"/proxy{path}"), timeout=5)
    assert response.status_code == 200
    assert response.content == b"".join(PAGES[path])


@contextmanager
def split_upstream() -> Iterator[str]:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), SplitHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever)
    upstream_thread.start()
    try:
        yield f"http://127.0.0.1:{upstream.server_port}"
    finally:
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join()


class SplitHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = PAGES[self.path]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(b"".join(body))))
        self.end_headers()
        for part in body:
            self.wfile.write(part)
            self.wfile.flush()
            time.sleep(0.05)

    def log_message(self, format: str, *args: object) -> None:
        pass
