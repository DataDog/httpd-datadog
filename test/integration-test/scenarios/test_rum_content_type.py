"""RUM must only modify responses whose media type is HTML."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

import pytest
import requests

from helper import make_configuration, save_configuration


@pytest.mark.requires_rum
@pytest.mark.parametrize("proxied", [False, True], ids=["static", "proxy"])
def test_rum_respects_response_content_type(server, log_dir, module_path, proxied):
    javascript = b"var editorHtml = '<html><head></head><body>Editor</body></html>';\n"
    html = b"<!DOCTYPE html><html><head><title>Page</title></head><body>Page</body></html>"
    responses = {
        "editor.js": ("application/javascript", javascript, False),
        "editor.txt": ("text/plain", javascript, False),
        "editor.json": ("application/json", javascript, False),
        "editor.lookalike": ("text/htmlish", javascript, False),
        "editor.unknown": (None, javascript, False),
        "index.html": ("text/html", html, True),
        "index.html_utf8": ("text/html; charset=utf-8", html, True),
        "index.html_mixed": ("TeXt/HtMl; charset=UTF-8", html, True),
    }

    class UpstreamHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.split("?", 1)[0].lstrip("/")
            content_type, body, _ = responses[name]
            self.send_response(200)
            if content_type is not None:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    upstream = None
    upstream_thread = None
    conf_path = str(Path(log_dir) / "httpd.conf")
    with tempfile.TemporaryDirectory(prefix="rum-content-type-") as docroot:
        # Apache workers must be able to read these temporary static assets.
        Path(docroot).chmod(0o755)
        for name, (_, body, _) in responses.items():
            path = Path(docroot) / name
            path.write_bytes(body)
            path.chmod(0o644)

        try:
            proxy_configuration = ""
            prefix = "/"
            if proxied:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
                upstream_thread = threading.Thread(target=upstream.serve_forever)
                upstream_thread.start()
                proxy_configuration = f"""
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
ProxyRequests Off
ProxyPass /upstream/ http://127.0.0.1:{upstream.server_port}/
"""
                prefix = "/upstream/"

            config = {
                "path": "conf/rum_content_type.conf",
                "var": {
                    "htdoc_dir": docroot,
                    "proxy_configuration": proxy_configuration,
                },
            }
            save_configuration(make_configuration(config, log_dir, module_path), conf_path)
            assert server.check_configuration(conf_path)
            assert server.load_configuration(conf_path)

            for name, (content_type, body, expect_injected) in responses.items():
                response = requests.get(server.make_url(f"{prefix}{name}?v=1"), timeout=5)
                assert response.status_code == 200, name
                actual_type = response.headers.get("Content-Type")
                if content_type is None:
                    assert actual_type is None, name
                else:
                    assert actual_type is not None, name
                    assert actual_type.lower() == content_type.lower(), name
                if expect_injected:
                    assert b"DD_RUM" in response.content, name
                    assert response.headers.get("x-datadog-sdk-injected") == "1", name
                else:
                    assert response.content == body, name
                    assert response.headers.get("x-datadog-sdk-injected") != "1", name
        finally:
            server.stop(conf_path)
            if upstream is not None:
                upstream.shutdown()
                upstream.server_close()
                upstream_thread.join()
