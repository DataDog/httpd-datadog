"""RUM must handle an HTML body split at any point across buckets."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration

# Each page is sent in two writes, split inside a possible `</head>` tag.
PAGES = {
    "/head": [b"<html><head><title>t</title></he", b"ad><body>ok</body></html>"],
    "/no-head": [b"<html><body><", b"div>ok</div></body></html>"],
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
            snippet_length = assert_injected_once(server)
            assert_not_injected_and_padded(server, snippet_length)
            assert_head_request_has_no_body(server)
        finally:
            server.stop(conf_path)


def assert_injected_once(server: Server) -> int:
    response = requests.get(server.make_url("/proxy/head"), timeout=5)
    assert response.status_code == 200
    pattern = (
        re.escape(b"<html><head><title>t</title>")
        + rb"\s*<script>.*DD_RUM.*</script>\s*"
        + re.escape(b"</head><body>ok</body></html>")
    )
    assert re.fullmatch(pattern, response.content, re.DOTALL), response.content
    return len(response.content) - len(b"".join(PAGES["/head"]))


def assert_not_injected_and_padded(server: Server, snippet_length: int) -> None:
    # The injector pads with spaces when it finds no injection point.
    response = requests.get(server.make_url("/proxy/no-head"), timeout=5)
    assert response.status_code == 200
    assert response.content == b"".join(PAGES["/no-head"]) + b" " * snippet_length


def assert_head_request_has_no_body(server: Server) -> None:
    # HTTP clients never read a HEAD body, so read the raw response.
    url = urlsplit(server.make_url("/proxy/no-head"))
    with socket.create_connection((url.hostname, url.port), timeout=5) as connection:
        connection.sendall(b"HEAD /proxy/no-head HTTP/1.0\r\nHost: localhost\r\n\r\n")
        response = b"".join(iter(lambda: connection.recv(4096), b""))
    assert response.startswith(b"HTTP/1.1 200 "), response
    assert response.endswith(b"\r\n\r\n"), response


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
        self.send_headers()
        for part in PAGES[self.path]:
            self.wfile.write(part)
            self.wfile.flush()
            time.sleep(0.05)

    def do_HEAD(self) -> None:
        self.send_headers()

    def send_headers(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(b"".join(PAGES[self.path]))))
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass
