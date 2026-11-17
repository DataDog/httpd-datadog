"""Check RUM output through Apache's streaming proxy."""

from collections.abc import Iterator
from contextlib import ExitStack
import gzip
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import tempfile
import time

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from upstream import upstream_proxy


# Short streams stay under 68 bytes. mod_deflate skips a complete response that
# small, but a later chunk keeps it from seeing the whole response at once.
STREAMS_WITH_CLOSING_TAG = {
    "split": [b"<html><head><title>Page</title></he", b"ad><body>Page</body></html>"],
    "charset-split": [
        b'<html><head><meta charset="utf-8"></he',
        b"ad><body>Hello</body></html>",
    ],
    "false-prefix": [b"<html><head></he", b"ader></head><body>Page</body></html>"],
    "large": [b"<html><head></head><body>" + b"0123456789" * 10000 + b"</body></html>"],
}
STREAMS_WITHOUT_CLOSING_TAG = {
    "eof": [b"<html><head><title>Page</title></he", b"ader></he"],
    "eof-long": [b"<html><head><title>" + b"Page " * 20 + b"</title></he", b"ader></he"],
    "charset-eof": [b'<html><head><meta charset="utf-8"></he', b"ader></he"],
    "charset-eof-long": [
        b'<html><head><meta charset="utf-8"><title>' + b"Page " * 20 + b"</title></he",
        b"ader></he",
    ],
    "fragment": [b"<div>Page", b"</div>"],
}
STREAMS = {**STREAMS_WITH_CLOSING_TAG, **STREAMS_WITHOUT_CLOSING_TAG}
PRECOMPRESSED_BODY = gzip.compress(b"".join(STREAMS["charset-split"]), mtime=0)


class StreamingUpstream(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        compressed = self.path == "/precompressed"
        chunks = (
            [PRECOMPRESSED_BODY[:20], PRECOMPRESSED_BODY[20:]]
            if compressed
            else STREAMS[self.path.lstrip("/")]
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(sum(map(len, chunks))))
        self.end_headers()
        for index, chunk in enumerate(chunks):
            if index > 0:
                # Let Apache pass the previous chunk on its own.
                time.sleep(0.1)
            self.wfile.write(chunk)
            self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(params=["no-deflate", "deflate-identity", "deflate-gzip"])
def mode(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def streaming_proxy(server: Server, log_dir: str, module_path: str, mode: str) -> Iterator[Server]:
    conf_path = str(Path(log_dir) / "httpd.conf")
    with ExitStack() as cleanup:
        docroot = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="rum-streaming-"))
        proxy = cleanup.enter_context(upstream_proxy(StreamingUpstream))
        if mode != "no-deflate":
            proxy += "\nLoadModule deflate_module modules/mod_deflate.so\nSetOutputFilter DEFLATE\n"
        cleanup.callback(server.stop, conf_path)
        configuration = {
            "path": Path(__file__).parent / "conf/rum_content_type.conf",
            "var": {"htdoc_dir": docroot, "proxy_configuration": proxy},
        }
        save_configuration(make_configuration(configuration, log_dir, module_path), conf_path)
        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)
        yield server


def fetch_stream(proxy: Server, stream_name: str, mode: str) -> bytes:
    response = requests.get(
        proxy.make_url(f"/upstream/{stream_name}"),
        headers={"Accept-Encoding": "identity" if mode == "deflate-identity" else "gzip"},
        timeout=3,
    )
    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") == ("gzip" if mode == "deflate-gzip" else None)
    return response.content


@pytest.mark.requires_rum
@pytest.mark.parametrize("stream_name", STREAMS_WITH_CLOSING_TAG)
def test_rum_streaming_injects_before_closing_tag(
    streaming_proxy: Server, stream_name: str, mode: str
) -> None:
    content = fetch_stream(streaming_proxy, stream_name, mode)
    body = b"".join(STREAMS[stream_name])
    closing = body.find(b"</head>")
    added = len(content) - len(body)
    assert added > 0
    assert content[:closing] == body[:closing]
    assert b"DD_RUM" in content[closing : closing + added]
    assert content[closing + added :] == body[closing:]


@pytest.mark.requires_rum
@pytest.mark.parametrize("stream_name", STREAMS_WITHOUT_CLOSING_TAG)
def test_rum_streaming_keeps_body_without_closing_tag(
    streaming_proxy: Server, stream_name: str, mode: str
) -> None:
    assert fetch_stream(streaming_proxy, stream_name, mode) == b"".join(STREAMS[stream_name])


@pytest.mark.requires_rum
@pytest.mark.parametrize("mode", ["no-deflate", "deflate-gzip"], indirect=True)
def test_rum_streaming_keeps_precompressed_body(streaming_proxy: Server) -> None:
    with requests.get(
        streaming_proxy.make_url("/upstream/precompressed"),
        headers={"Accept-Encoding": "gzip"},
        stream=True,
        timeout=3,
    ) as response:
        assert response.status_code == 200
        assert response.headers.get("Content-Encoding") == "gzip"
        assert response.headers.get("x-datadog-rum-injected") != "1"
        assert response.raw.read() == PRECOMPRESSED_BODY
