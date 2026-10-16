"""Check RUM output through Apache's streaming proxy."""

from collections.abc import Iterator
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import time

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from test_rum_content_type import static_docroot, upstream_proxy


STREAMS = {
    "split": [b"<html><head><title>Page</title></he", b"ad><body>Page</body></html>"],
    "false-prefix": [b"<html><head></he", b"ader></head><body>Page</body></html>"],
    "eof": [b"<html><head><title>Page</title></he"],
    "large": [b"<html><head></head><body>" + b"0123456789" * 10000 + b"</body></html>"],
}


class StreamingUpstream(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        chunks = STREAMS[self.path.lstrip("/")]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(sum(map(len, chunks))))
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(chunk)
            self.wfile.flush()
            time.sleep(0.1)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def streaming_proxy(server: Server, log_dir: str, module_path: str) -> Iterator[Server]:
    conf_path = str(Path(log_dir) / "httpd.conf")
    with ExitStack() as cleanup:
        docroot = cleanup.enter_context(static_docroot())
        proxy = cleanup.enter_context(upstream_proxy(StreamingUpstream))
        cleanup.callback(server.stop, conf_path)
        configuration = {
            "path": Path(__file__).parent / "conf/rum_content_type.conf",
            "var": {"htdoc_dir": docroot, "proxy_configuration": proxy},
        }
        save_configuration(make_configuration(configuration, log_dir, module_path), conf_path)
        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)
        yield server


@pytest.mark.requires_rum
@pytest.mark.parametrize("mode", STREAMS)
def test_rum_streaming(streaming_proxy: Server, mode: str) -> None:
    response = requests.get(streaming_proxy.make_url(f"/upstream/{mode}"), timeout=3)
    assert response.status_code == 200
    body = b"".join(STREAMS[mode])
    closing = body.find(b"</head>")
    if closing < 0:
        assert response.content[: len(body)] == body
        padding = response.content[len(body) :]
        assert padding and padding.strip(b" ") == b""
    else:
        added = len(response.content) - len(body)
        assert added > 0
        assert response.content[:closing] == body[:closing]
        assert b"DD_RUM" in response.content[closing : closing + added]
        assert response.content[closing + added :] == body[closing:]
