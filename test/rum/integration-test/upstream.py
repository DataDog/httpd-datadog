"""Local HTTP upstream for tests that go through Apache's proxy."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


@contextmanager
def upstream_proxy(handler_type: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    """Serve handler_type locally and yield the directives that proxy /upstream/ to it."""
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
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
