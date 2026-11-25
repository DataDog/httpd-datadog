"""Check RUM output through Apache's streaming proxy."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
import gzip
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import tempfile
import threading

import pytest
import requests

from conftest import Server
from helper import make_configuration, save_configuration
from upstream import upstream_proxy


# Short streams stay under 68 bytes. mod_deflate skips a complete response that
# small, so the upstream waits for the headers before the next chunk.
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
    # The client sets the first once it has the headers. The upstream sets the
    # second if it gave up waiting.
    headers_received = threading.Event()
    missed_headers = threading.Event()

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
            # Once Apache sent the headers, mod_deflate has chosen to compress
            # without seeing the end of the body.
            if index > 0 and not self.headers_received.wait(2):
                self.missed_headers.set()
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
    StreamingUpstream.headers_received = threading.Event()
    StreamingUpstream.missed_headers = threading.Event()
    with ExitStack() as cleanup:
        docroot = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="rum-streaming-"))
        proxy = cleanup.enter_context(upstream_proxy(StreamingUpstream))
        if mode == "inflate-deflate":
            proxy += (
                "\nLoadModule deflate_module modules/mod_deflate.so"
                "\nLoadModule filter_module modules/mod_filter.so"
                "\nAddOutputFilterByType INFLATE;DEFLATE text/html\n"
            )
        elif mode != "no-deflate":
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


@contextmanager
def open_stream(proxy: Server, path: str, accept_encoding: str) -> Iterator[requests.Response]:
    with requests.get(
        proxy.make_url(path),
        headers={"Accept-Encoding": accept_encoding},
        stream=True,
        timeout=3,
    ) as response:
        assert not StreamingUpstream.missed_headers.is_set(), "Apache held the headers"
        StreamingUpstream.headers_received.set()
        yield response
    assert not StreamingUpstream.missed_headers.is_set(), "upstream gave up waiting for headers"


def fetch_stream(proxy: Server, stream_name: str, mode: str) -> bytes:
    accept_encoding = "identity" if mode == "deflate-identity" else "gzip"
    with open_stream(proxy, f"/upstream/{stream_name}", accept_encoding) as response:
        assert response.status_code == 200
        expected_encoding = "gzip" if mode == "deflate-gzip" else None
        assert response.headers.get("Content-Encoding") == expected_encoding
        assert response.headers.get("x-datadog-rum-injected") == "1"
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
    with open_stream(streaming_proxy, "/upstream/precompressed", "gzip") as response:
        assert response.status_code == 200
        assert response.headers.get("Content-Encoding") == "gzip"
        assert response.headers.get("x-datadog-rum-injected") != "1"
        assert response.raw.read() == PRECOMPRESSED_BODY


@pytest.mark.requires_rum
@pytest.mark.parametrize("mode", ["inflate-deflate"], indirect=True)
def test_rum_streaming_injects_after_inflate(streaming_proxy: Server) -> None:
    with open_stream(streaming_proxy, "/upstream/precompressed", "gzip") as response:
        assert response.status_code == 200
        assert response.headers.get("Content-Encoding") == "gzip"
        assert response.headers.get("x-datadog-rum-injected") == "1"
        assert b"DD_RUM" in response.content
