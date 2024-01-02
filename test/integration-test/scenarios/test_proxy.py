#!/usr/bin/env python3
"""
Test related to proxy
"""
from queue import Queue
import time
import requests
import pytest
import os
from helper import relpath, make_configuration, save_configuration

from aiohttp import web
import asyncio
import threading


class AioHTTPServer:
    def __init__(self, app, host, port) -> None:
        self._thread = None
        self._stop = asyncio.Event()
        self._host = host
        self._port = port
        self._app = app
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def internal_run(self) -> None:
        runner = web.AppRunner(self._app)
        self.loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, self._host, self._port)
        self.loop.run_until_complete(site.start())
        self.loop.run_until_complete(self._stop.wait())
        self.loop.run_until_complete(self._app.cleanup())
        self.loop.close()

    def run(self) -> None:
        self._thread = threading.Thread(target=self.internal_run)
        self._thread.start()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self._stop.set)


def test_http_proxy(server, agent, log_dir, module_path):
    """
    Verify proxified HTTP requests propagate tracing context
    """

    # TODO: support `with` syntax
    def make_temporary_http_server(host: str, port: int):
        q = Queue()

        async def index(request):
            q.put(request.headers)
            return web.Response(text="Hello, Dog!")

        app = web.Application()
        app.add_routes([web.get("/", index)])

        return q, AioHTTPServer(app, host, port)

    host = "127.0.0.1"
    port = 8081
    queue, http_server = make_temporary_http_server(host, port)
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
    server.stop(conf_path)

    assert not queue.empty()

    upstream_headers = queue.get()
    assert "x-datadog-trace-id" in upstream_headers
    assert "x-datadog-parent-id" in upstream_headers

    traces = agent.get_traces(timeout=5)
    assert len(traces) == 1


@pytest.mark.skip(reason="WIP")
def test_sampling_delegation(server, agent):
    """
    Verify `DatadogDelegateSampling` delegate the sampling decision to the downstream service.

    When sampling delegation is `On`, we expect the downstream service to receive the
    `x-datadog-delegate-trace-sampling` header, then dependending of the result return by the
    downstream service, the sampling priority of the root span should be impacted.

    When `Off`, no `x-datadog-delegate-tracing` header should be sent.
    """

    def make_http_server_accept_delegation():
        q = Queue()

        async def index(request):
            q.put(request.headers)
            return web.Response(text="Hello, Dog!")

        app = web.Application()
        app.add_routes([web.get("/", index)])

        return q, AioHTTPServer(app, "localhost", 8081)

    queue, http_server = make_http_server_accept_delegation()
    http_server.run()

    # assert server.load_configuration(relpath("conf/proxy.conf"))
    r = requests.get(server.make_url("/delegate"), timeout=2)
    assert r.status_code == 200

    http_server.stop()

    assert not queue.empty()

    downstream_headers = queue.get()
    assert "x-datadog-delegate-tracing" in downstream_headers

    traces = agent.get_traces(timeout=5)
    assert len(traces) == 1

    root_span = traces[0][0]
    assert root_span["meta"]["_dd.is_sampling_decider"] == "1"
