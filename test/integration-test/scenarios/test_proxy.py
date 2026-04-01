#!/usr/bin/env python3
"""
Test related to proxy
"""
from queue import Queue
import requests
import os
from aiohttp import web
from helper import relpath, make_configuration, save_configuration, AioHTTPServer, free_port


def test_http_proxy(server, agent, log_dir, module_path):
    """
    Verify proxified HTTP requests propagate tracing context
    """
    host = "127.0.0.1"
    port = free_port()
    q = Queue()

    async def index(request):
        q.put(request.headers)
        return web.Response(text="Hello, Dog!")

    app = web.Application()
    app.add_routes([web.get("/", index)])
    http_server = AioHTTPServer(app, host, port)
    http_server.run()

    config = {
        "path": relpath("conf/proxy.conf"),
        "var": {"upstream_url": f"http://{host}:{port}"},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    r = requests.get(server.make_url("/http"), timeout=2)
    assert r.status_code == 200

    http_server.stop()
    assert server.stop(conf_path)

    assert not q.empty()

    upstream_headers = q.get()
    assert "x-datadog-trace-id" in upstream_headers
    assert "x-datadog-parent-id" in upstream_headers
    # Non-RUM build should not leak injection-pending header
    assert "x-datadog-rum-injection-pending" not in upstream_headers

    traces = agent.get_traces(timeout=5)
    assert len(traces) == 1
