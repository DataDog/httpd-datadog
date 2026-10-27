"""Check RUM output through Apache's streaming proxy."""

from collections.abc import Iterator
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import tempfile
import time

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from upstream import upstream_proxy


STREAMS_WITH_CLOSING_TAG = {
    "split": [b"<html><head><title>Page</title></he", b"ad><body>Page</body></html>"],
    "false-prefix": [b"<html><head></he", b"ader></head><body>Page</body></html>"],
    "large": [b"<html><head></head><body>" + b"0123456789" * 10000 + b"</body></html>"],
}
STREAMS_WITHOUT_CLOSING_TAG = {
    "eof": [b"<html><head><title>Page</title></he"],
}
STREAMS = {**STREAMS_WITH_CLOSING_TAG, **STREAMS_WITHOUT_CLOSING_TAG}


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
        docroot = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="rum-streaming-"))
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


def fetch_stream(proxy: Server, stream_name: str) -> bytes:
    response = requests.get(proxy.make_url(f"/upstream/{stream_name}"), timeout=3)
    assert response.status_code == 200
    return response.content


@pytest.mark.requires_rum
@pytest.mark.parametrize("stream_name", STREAMS_WITH_CLOSING_TAG)
def test_rum_streaming_injects_before_closing_tag(streaming_proxy: Server, stream_name: str) -> None:
    content = fetch_stream(streaming_proxy, stream_name)
    body = b"".join(STREAMS[stream_name])
    closing = body.find(b"</head>")
    added = len(content) - len(body)
    assert added > 0
    assert content[:closing] == body[:closing]
    assert b"DD_RUM" in content[closing : closing + added]
    assert content[closing + added :] == body[closing:]


@pytest.mark.requires_rum
@pytest.mark.parametrize("stream_name", STREAMS_WITHOUT_CLOSING_TAG)
def test_rum_streaming_keeps_body_without_closing_tag(streaming_proxy: Server, stream_name: str) -> None:
    content = fetch_stream(streaming_proxy, stream_name)
    body = b"".join(STREAMS[stream_name])
    assert content[: len(body)] == body
    padding = content[len(body) :]
    assert padding and padding.strip(b" ") == b""
