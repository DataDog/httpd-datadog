import asyncio
import os
import socket
import threading
from datetime import datetime
from string import Template
from pathlib import Path
import tempfile
from contextlib import contextmanager
from typing import Self

import requests
from aiohttp import web


def relpath(p: str) -> str:
    return Path(__file__).parent / p


def save_configuration(content: str, destination: str) -> None:
    with open(destination, "w") as f:
        f.write(content)


def make_configuration(config, log_dir, module_path):
    HTTPD_CONF_TEMPLATE = """# Apache httpd configuration
# Generated from XYZ
# For tests XYZ at $meta_date
# Values: $meta_values

Listen $port

LoadModule dir_module modules/mod_dir.so
LoadModule unixd_module modules/mod_unixd.so
LoadModule authz_core_module modules/mod_authz_core.so
LoadModule log_config_module modules/mod_log_config.so

LogLevel debug
ErrorLog $error_log_file

LogFormat "%h %l %u %t \\"%r\\" %>s %b" common
CustomLog $access_log_file common

PidFile $pid_file

DocumentRoot $htdoc_dir
DirectoryIndex index.html
"""

    def load_template(template_file: str) -> Template:
        content = HTTPD_CONF_TEMPLATE

        with open(template_file, "r") as f:
            content += f.read()

        return Template(content)

    def substitute(template, opts):
        pp_values = ""
        for k, v in opts.items():
            pp_values += f"\n# - {k}: {v}"

        opts["meta_date"] = datetime.now()
        opts["meta_values"] = pp_values
        return template.substitute(opts)

    server_opts = {
        "port": "8080",
        "htdoc_dir": relpath("htdocs"),
        "access_log_file": f"{os.path.join(log_dir, 'access_log')}",
        "error_log_file": f"{os.path.join(log_dir, 'error_log')}",
        "pid_file": f"{os.path.join(log_dir, 'httpd.pid')}",
        "load_datadog_module": f"LoadModule datadog_module {module_path}",
    }
    server_opts.update(config["var"])
    template = load_template(relpath(config["path"]))
    conf_content = substitute(template, server_opts)
    return conf_content


@contextmanager
def make_temporary_configuration(config, module_path):
    with tempfile.NamedTemporaryFile() as f:
        save_configuration(make_configuration(config, "", module_path), f.name)
        yield f.name


def free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AioHTTPServer:
    """Lightweight aiohttp server that runs in a background thread."""

    _thread: threading.Thread | None
    _stop: asyncio.Event
    _host: str
    _port: int
    _app: web.Application
    loop: asyncio.AbstractEventLoop

    def __init__(self, app: web.Application, host: str, port: int) -> None:
        self._thread = None
        self._stop = asyncio.Event()
        self._host = host
        self._port = port
        self._app = app
        self.loop = asyncio.new_event_loop()

    def internal_run(self) -> None:
        runner = web.AppRunner(self._app)
        self.loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, self._host, self._port, shutdown_timeout=1.0)
        self.loop.run_until_complete(site.start())
        self.loop.run_until_complete(self._stop.wait())
        self.loop.run_until_complete(runner.cleanup())
        self.loop.close()

    def run(self) -> None:
        self._thread = threading.Thread(target=self.internal_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def __enter__(self) -> Self:
        self.run()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


def assert_rum_injected(response: requests.Response) -> None:
    """
    Verify that RUM SDK was injected into the response.

    Checks for:
    1. RUM SDK script in response body
    2. Injection marker header
    """
    content = response.text

    # Check for Datadog RUM SDK markers
    # The SDK injects a script tag with the browser SDK
    rum_markers = [
        "datadoghq-browser-sdk",
        "DD_RUM",
        "applicationId",
        "clientToken",
    ]

    found_markers = [marker for marker in rum_markers if marker in content]

    assert len(found_markers) > 0, (
        f"Expected RUM SDK to be injected but found no markers. "
        f"Response length: {len(content)}, "
        f"Content preview: {content[:200]}"
    )

    # Check for injection header
    injection_header = response.headers.get("x-datadog-sdk-injected")
    assert injection_header == "1", (
        f"Expected x-datadog-sdk-injected header to be '1' but got '{injection_header}'"
    )


def assert_rum_not_injected(response: requests.Response) -> None:
    """
    Verify that RUM SDK was NOT injected into the response.

    Checks that:
    1. RUM SDK script is absent from response body
    2. Injection marker header is not set or is set to a value other than "1"
    """
    content = response.text

    # Check that Datadog RUM SDK markers are NOT present
    rum_markers = [
        "datadoghq-browser-sdk",
        "DD_RUM",
    ]

    found_markers = [marker for marker in rum_markers if marker in content]

    assert len(found_markers) == 0, (
        f"Expected RUM SDK NOT to be injected but found markers: {found_markers}. "
        f"Content preview: {content[:500]}"
    )

    # Check injection header is not set to "1"
    injection_header = response.headers.get("x-datadog-sdk-injected")
    assert injection_header != "1", (
        f"Expected x-datadog-sdk-injected header NOT to be '1' but got '{injection_header}'"
    )
