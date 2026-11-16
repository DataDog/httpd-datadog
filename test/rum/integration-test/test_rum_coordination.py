"""Reserve streaming injection at the client-facing Apache before proxying."""

from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import tempfile
import threading

import pytest
import requests

from conftest import DockerProc, Server
from helper import free_port, make_configuration, save_configuration
from upstream import upstream_proxy


PENDING = "x-datadog-rum-injection-pending"
INJECTED = "x-datadog-rum-injected"
HEAD = b'<html><head><meta charset="utf-8">'
STREAMS = {
    "short": [HEAD + b"</he", b"ad><body>Hello</body></html>"],
    "long": [HEAD + b"<!--" + b"x" * 18000 + b"--></he", b"ad><body>Hello</body></html>"],
    "no-point": [HEAD + b"<!--" + b"x" * 18000 + b"--></h", b"e"],
}
PAGE = HEAD + b"</head><body>Hello</body></html>"
pytestmark = pytest.mark.requires_rum


@pytest.fixture
def rum_chain(request, log_dir, module_path):
    release = threading.Event()

    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            chunks = STREAMS[self.path.lstrip("/")]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(sum(map(len, chunks))))
            self.send_header("X-Test-Pending", self.headers.get(PENDING, "absent"))
            self.end_headers()
            self.wfile.write(chunks[0])
            self.wfile.flush()
            if release.wait(timeout=10):
                self.wfile.write(chunks[1])

        def log_message(self, format, *args):
            pass

    with ExitStack() as cleanup:
        upstream = cleanup.enter_context(upstream_proxy(Upstream))
        cleanup.callback(release.set)

        def start(frontend_enabled="On", backend_enabled="On", target_enabled="On"):
            backend = None
            for app_id, enabled in [
                ("test-app", backend_enabled), ("front-app", frontend_enabled)
            ]:
                root = Path(log_dir) / app_id
                root.mkdir()
                docroot = Path(cleanup.enter_context(
                    tempfile.TemporaryDirectory(prefix="rum-coordination-")
                ))
                docroot.chmod(0o755)
                (docroot / "page.html").write_bytes(PAGE)
                (docroot / "include.shtml").write_text('<!--#include virtual="/page.html" -->')
                (docroot / "off").mkdir()
                (docroot / "off/page.html").write_bytes(PAGE)
                port = free_port()
                proxy = upstream
                if backend:
                    proxy = f"""
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
ProxyPass /upstream/ {backend.make_url('/upstream/')}
"""
                configuration = {
                    "path": Path(__file__).parent / "conf/rum_coordination.conf",
                    "var": {
                        "port": port, "htdoc_dir": docroot, "app_id": app_id,
                        "enabled": enabled, "target_enabled": target_enabled,
                        "proxy_configuration": proxy,
                    },
                }
                conf_path = str(root / "httpd.conf")
                save_configuration(
                    make_configuration(configuration, str(root), module_path), conf_path
                )
                apache = Server(
                    "127.0.0.1", port,
                    DockerProc(request.config.getoption("--bin-path")), conf_path,
                )
                cleanup.callback(apache.stop, conf_path)
                assert apache.check_configuration(conf_path)
                assert apache.load_configuration(conf_path)
                if backend is None:
                    backend = apache
            return apache, backend, release

        yield start


def read_stream(apache, release, name, pending=None, path=None):
    headers = {} if pending is None else {PENDING: pending}
    with requests.get(apache.make_url(path or f"/upstream/{name}"), headers=headers,
                      stream=True, timeout=3) as response:
        try:
            # The closing tag is still held upstream: success cannot be claimed yet.
            assert INJECTED not in response.headers
            first = response.raw.read(1)
            assert first == b"<"
        finally:
            release.set()
        content = first + response.raw.read()
        return response, content


def assert_one_app(content, app_id):
    assert content.count(b"window.DD_RUM.init(") == 1
    assert content.count(b"https://www.datadoghq-browser-agent.com/") == 1
    assert f'"applicationId":"{app_id}"'.encode() in content
    other_app = "test-app" if app_id == "front-app" else "front-app"
    assert f'"applicationId":"{other_app}"'.encode() not in content


@pytest.mark.parametrize("name", ["short", "long"])
@pytest.mark.parametrize("pending", [None, "0"])
def test_streaming_chain_reserves_frontend_injection(rum_chain, name, pending):
    frontend, _, release = rum_chain()
    response, content = read_stream(frontend, release, name, pending)
    assert response.status_code == 200
    assert response.headers["X-Test-Pending"] == "1"
    assert_one_app(content, "front-app")
    body = b"".join(STREAMS[name])
    closing = body.index(b"</head>")
    assert content[:closing] == body[:closing]
    assert content.endswith(body[closing:])


@pytest.mark.parametrize("frontend_enabled,backend_enabled,expected_app", [
    ("Off", "On", "test-app"), ("On", "Off", "front-app"), ("Off", "Off", None),
])
def test_streaming_chain_respects_disabled_rum(
    rum_chain, frontend_enabled, backend_enabled, expected_app
):
    frontend, _, release = rum_chain(frontend_enabled, backend_enabled)
    response, content = read_stream(frontend, release, "long")
    assert response.status_code == 200
    assert response.headers["X-Test-Pending"] == ("1" if expected_app else "absent")
    if expected_app:
        assert_one_app(content, expected_app)
    else:
        assert content == b"".join(STREAMS["long"])


@pytest.mark.parametrize("name,pending", [("no-point", None), ("long", "1")])
def test_streaming_chain_does_not_claim_or_add_an_injection(rum_chain, name, pending):
    frontend, _, release = rum_chain()
    response, content = read_stream(frontend, release, name, pending)
    assert response.status_code == 200
    assert response.headers["X-Test-Pending"] == "1"
    assert content == b"".join(STREAMS[name])


@pytest.mark.parametrize("path,status", [("/missing", 404), ("/include.shtml", 200)], ids=["redirect", "ssi"])
@pytest.mark.parametrize("target_enabled", ["On", "Off"])
@pytest.mark.parametrize("pending", [None, "1"])
def test_local_requests_keep_the_received_reservation(
    rum_chain, path, status, target_enabled, pending
):
    frontend, _, _ = rum_chain(target_enabled=target_enabled)
    headers = {} if pending is None else {PENDING: pending}
    response = requests.get(frontend.make_url(path), headers=headers, timeout=3)
    assert response.status_code == status
    if target_enabled == "On" and pending is None:
        assert_one_app(response.content, "front-app")
    else:
        assert response.content == PAGE
        assert INJECTED not in response.headers


def test_disabled_location_keeps_body(rum_chain):
    frontend, _, _ = rum_chain()
    response = requests.get(frontend.make_url("/off/page.html"), timeout=3)
    assert response.status_code == 200
    assert response.content == PAGE
    assert INJECTED not in response.headers


@pytest.mark.parametrize("pending", [None, "1"])
def test_redirect_to_disabled_proxy_releases_local_reservation(rum_chain, pending):
    frontend, _, release = rum_chain(frontend_enabled="Off")
    response, content = read_stream(
        frontend, release, "short", pending, path="/missing-proxy"
    )
    assert response.status_code == 200
    if pending is None:
        assert_one_app(content, "test-app")
    else:
        assert content == b"".join(STREAMS["short"])
