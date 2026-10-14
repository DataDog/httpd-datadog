"""RUM must only modify responses whose media type is HTML."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
from typing import NamedTuple

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration

RUM_TEST_DIR = Path(__file__).parent


class ExpectedResponse(NamedTuple):
    content_type: str | None
    body: bytes
    injected: bool


JAVASCRIPT = b"var editorHtml = '<html><head></head><body>Editor</body></html>';\n"
HTML = b"<!DOCTYPE html><html><head><title>Page</title></head><body>Page</body></html>"
RESPONSES = {
    "editor.js": ExpectedResponse("application/javascript", JAVASCRIPT, False),
    "editor.txt": ExpectedResponse("text/plain", JAVASCRIPT, False),
    "editor.json": ExpectedResponse("application/json", JAVASCRIPT, False),
    "editor.lookalike": ExpectedResponse("text/htmlish", JAVASCRIPT, False),
    "editor.unknown": ExpectedResponse(None, JAVASCRIPT, False),
    "index.html": ExpectedResponse("text/html", HTML, True),
    "index.html_utf8": ExpectedResponse("text/html; charset=utf-8", HTML, True),
    "index.html_mixed": ExpectedResponse("TeXt/HtMl; charset=UTF-8", HTML, True),
}


@pytest.mark.requires_rum
@pytest.mark.parametrize("proxied", [False, True], ids=["static", "proxy"])
def test_rum_respects_response_content_type(
    server: Server, log_dir: str, module_path: str, proxied: bool
) -> None:
    conf_path = str(Path(log_dir) / "httpd.conf")
    with ExitStack() as cleanup:
        docroot = cleanup.enter_context(static_docroot())
        proxy_configuration = cleanup.enter_context(upstream_proxy()) if proxied else ""
        cleanup.callback(server.stop, conf_path)
        config = {
            "path": RUM_TEST_DIR / "conf/rum_content_type.conf",
            "var": {"htdoc_dir": docroot, "proxy_configuration": proxy_configuration},
        }
        save_configuration(make_configuration(config, log_dir, module_path), conf_path)
        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)

        prefix = "/upstream/" if proxied else "/"
        for name, expected in RESPONSES.items():
            response = requests.get(server.make_url(f"{prefix}{name}?v=1"), timeout=5)
            assert_rum_response(response, name, expected, proxied)


@contextmanager
def static_docroot() -> Iterator[str]:
    with tempfile.TemporaryDirectory(prefix="rum-content-type-") as docroot:
        # Apache workers must be able to read these temporary static assets.
        Path(docroot).chmod(0o755)
        for name, expected in RESPONSES.items():
            path = Path(docroot) / name
            path.write_bytes(expected.body)
            path.chmod(0o644)
        yield docroot


@contextmanager
def upstream_proxy(
    handler_type: type[BaseHTTPRequestHandler] | None = None,
) -> Iterator[str]:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), handler_type or UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever)
    upstream_thread.start()
    try:
        yield f"""
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
ProxyRequests Off
ProxyPass /upstream/ http://127.0.0.1:{upstream.server_port}/
"""
    finally:
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join()


class UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        name = self.path.split("?", 1)[0].lstrip("/")
        expected = RESPONSES[name]
        self.send_response(200)
        if expected.content_type is not None:
            self.send_header("Content-Type", expected.content_type)
        self.send_header("Content-Length", str(len(expected.body)))
        self.end_headers()
        body = expected.body
        if expected.injected:
            # Send headers and a body prefix before the injection point.
            split_at = body.index(b"</head>")
            self.wfile.write(body[:split_at])
            self.wfile.flush()
            time.sleep(0.05)
            body = body[split_at:]
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def assert_rum_response(
    response: requests.Response, name: str, expected: ExpectedResponse, proxied: bool
) -> None:
    assert response.status_code == 200, name
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        assert int(content_length) == len(response.content), name
    assert (
        lowercase(response.headers.get("Content-Type")) == lowercase(expected.content_type)
    ), name
    if expected.injected:
        assert b"DD_RUM" in response.content, name
        assert response.content.endswith(b"</body></html>"), name
        # Streaming proxy headers can be sent before injection.
        if not proxied:
            assert response.headers.get("x-datadog-sdk-injected") == "1", name
    else:
        assert response.content == expected.body, name
        assert response.headers.get("x-datadog-sdk-injected") != "1", name


def lowercase(value: str | None) -> str | None:
    return value and value.lower()
