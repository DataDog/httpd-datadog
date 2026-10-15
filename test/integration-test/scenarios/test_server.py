import errno
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

import conftest


@pytest.fixture
def stopping_server(monkeypatch):
    listener = MagicMock()
    monkeypatch.setattr(
        conftest,
        "socket",
        SimpleNamespace(
            socket=Mock(return_value=listener),
            SOL_SOCKET=socket.SOL_SOCKET,
            SO_REUSEADDR=socket.SO_REUSEADDR,
        ),
    )
    clock = SimpleNamespace(monotonic=Mock(return_value=0), sleep=Mock())
    monkeypatch.setattr(conftest, "time", clock)
    process = Mock()
    process.run.return_value.returncode = 0
    server = conftest.Server("127.0.0.1", 8080, process, "httpd.conf")
    return server, listener.__enter__.return_value, clock


@pytest.mark.ci
def test_stop_waits_for_port_release(stopping_server):
    server, listener, _ = stopping_server
    listener.bind.side_effect = [OSError(errno.EADDRINUSE, "Port is busy"), None]

    assert server.stop("httpd.conf")
    assert listener.bind.call_count == 2


@pytest.mark.ci
def test_stop_reports_shutdown_timeout(stopping_server):
    server, listener, clock = stopping_server
    listener.bind.side_effect = OSError(errno.EADDRINUSE, "Port is busy")
    clock.monotonic.side_effect = [0, 0, float("inf")]

    assert not server.stop("httpd.conf")
