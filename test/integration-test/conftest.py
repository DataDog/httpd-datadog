pytest_plugins = ["pytest_plugins.integration_helpers"]

import tempfile
import shutil
import argparse
import subprocess
import sys
import re
import os
import typing
import time
import uuid
from ddapm_test_agent.agent import make_app
from aiohttp import web
import asyncio
import threading

import requests
from datetime import datetime
import pytest

from ddapm_test_agent.agent import make_app
from aiohttp import web

CWD = os.path.dirname(__file__)


class DockerProc:
    def __init__(self, container_name: str) -> None:
        self._name = container_name

    # TODO: Fix typing
    def run(self, cmd: str) -> typing.Any:
        cmd = f"{self._name} {cmd}"
        print(f"[debug] {cmd}")
        return subprocess.run(
            cmd,
            shell=True,
            check=False,
            capture_output=True,
        )


class Server:
    def __init__(self, host, port, proc, conf) -> None:
        self.host = host
        self.port = port
        self._proc = proc
        self._conf = conf

    def make_url(self, path: str) -> str:
        url = f"http://{self.host}"
        if self.port:
            url += f":{self.port}"
        url += path if path else "/"

        return url

    def check_directive(self, directive: str) -> bool:
        rc = self._proc.run(f'-C "{directive}" -t').returncode
        return rc == 0

    def check_configuration(self, conf_path: str) -> bool:
        if not os.path.exists(conf_path):
            raise Exception(f"Configuration not found: {conf_path}")

        result = self._proc.run(f"-f {conf_path} -t")
        if result.returncode != 0:
            print(f"[error] Configuration check failed:")
            print(f"[error] stdout: {result.stdout.decode('utf-8')}")
            print(f"[error] stderr: {result.stderr.decode('utf-8')}")
        return result.returncode == 0

    def load_configuration(self, conf_path: str) -> bool:
        if not os.path.exists(conf_path):
            raise Exception(f"Configuration not found: {conf_path}")

        # Start Apache as a daemon
        result = self._proc.run(f"-f {conf_path} -k start")
        if result.returncode != 0:
            print(f"[error] Apache startup failed:")
            print(f"[error] stdout: {result.stdout.decode('utf-8')}")
            print(f"[error] stderr: {result.stderr.decode('utf-8')}")
        return result.returncode == 0

    def stop(self, conf_path) -> None:
        rc = self._proc.run(f"-f {conf_path} -k stop").returncode
        return rc == 0


class AgentSession:
    def __init__(self, agent: typing.Any, token: str) -> None:
        self.agent_ = agent
        self.token_ = token

    def received_trace(self, timeout) -> bool:
        beg = datetime.now()
        while (datetime.now() - beg).total_seconds() < timeout:
            r = requests.get(
                f"http://{self.agent_.host}:{self.agent_.port}/test/session/traces?test_session_token={self.token_}"
            )
            if r.status_code == 200 and len(r.json()) >= 1:
                print(f"Received: {r.json()}")
                return True

            time.sleep(1)

        return False

    def get_traces(self, timeout) -> typing.Any:
        beg = datetime.now()
        while (datetime.now() - beg).total_seconds() < timeout:
            r = requests.get(
                f"http://{self.agent_.host}:{self.agent_.port}/test/session/traces?test_session_token={self.token_}"
            )
            if r.status_code == 200 and len(r.json()) >= 1:
                # print(f"Received: {r.json()}")
                return r.json()

            time.sleep(1)

        return []


class TestAgent:
    def __init__(self, host: str, port: int) -> None:
        self._stop = asyncio.Event()
        self.host = host
        self.port = port
        self._app = make_app(
            enabled_checks="",
            log_span_fmt="[{name}]",
            snapshot_dir="snapshot",
            snapshot_ci_mode=0,
            snapshot_ignored_attrs="",
            agent_url="",
            trace_request_delay=0.0,
            suppress_trace_parse_errors=False,
            pool_trace_check_failures=False,
            disable_error_responses=False,
            snapshot_removed_attrs="",
            snapshot_regex_placeholders="",
            vcr_cassettes_directory="",
            vcr_ci_mode=False,
            vcr_provider_map="",
            vcr_ignore_headers="",
            dd_site="",
            dd_api_key="",
            disable_llmobs_data_forwarding=False,
        )
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def internal_run(self) -> None:
        runner = web.AppRunner(self._app)
        self.loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, self.host, self.port)
        self.loop.run_until_complete(site.start())
        self.loop.run_until_complete(self._stop.wait())
        self.loop.run_until_complete(self._app.cleanup())
        self.loop.close()

    def run(self) -> None:
        self._thread = threading.Thread(target=self.internal_run)
        self._thread.start()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self._stop.set)
        self._thread.join()

    def new_session(self, token=None) -> AgentSession:
        if token is None:
            token = str(uuid.uuid4())

        r = requests.get(
            f"http://{self.host}:{self.port}/test/session/start?test_session_token={token}"
        )
        r.raise_for_status()

        return AgentSession(self, token)


def extant_file(x):
    """
    'Type' for argparse - checks that file exists but does not open.
    """
    x = os.path.abspath(x)
    if not os.path.exists(x):
        raise argparse.ArgumentTypeError("{0} does not exist".format(x))
    return x


def lazy_mkdir(path):
    def f():
        os.mkdir(path)
        return path

    return f


def pytest_addoption(parser, pluginmanager) -> None:
    """
    Allows plugins and conftest files to perform initial configuration.
    This hook is called for every plugin and initial conftest
    file after command line options have been parsed.
    """
    parser.addoption(
        "--bin-path",
        help="binary under test. Example: apachectl",
        required=False,
        type=extant_file,
    )
    parser.addoption(
        "--module-path",
        help="mod_datadog.so under test (auto-built for RUM tests)",
        required=False,
        type=extant_file,
    )
    parser.addoption(
        "--log-dir",
        help="Location of the directory that will be use to store log files",
    )


def pytest_configure(config):
    """
    This hook is called for every plugin and initial conftest file after command line options have been parsed
    """
    # Register custom markers
    config.addinivalue_line("markers", "smoke: marks tests as smoke tests")
    config.addinivalue_line(
        "markers",
        "ci: temporary marks for tests that are stable enough to be run in a CI environment",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    # Use module_path from plugin if auto-built, otherwise use command-line option
    if not hasattr(session.config, 'module_path') or session.config.module_path is None:
        session.config.module_path = session.config.getoption("--module-path")

    apachectl_bin = session.config.getoption("--bin-path")

    log_dir = session.config.getoption("--log-dir")
    if log_dir:
        if os.path.exists(log_dir):
            # TODO: Warn old logs will be removed and manage error
            shutil.rmtree(log_dir)
        os.mkdir(log_dir)
    else:
        log_dir = tempfile.mkdtemp(prefix="log-httpd-tests-", dir=".")

    session.config.log_dir = log_dir

    session.config.test_agent = TestAgent("127.0.0.1", 8136)
    session.config.test_agent.run()

    session.config.server = Server(
        host="127.0.0.1",
        port="8080",
        proc=DockerProc(apachectl_bin),
        conf="/usr/local/apache2/conf/httpd.conf",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    session.config.test_agent.stop()


def pytest_runtest_setup(item: pytest.Item) -> None:
    token = f"{item.name}-{uuid.uuid4()}"
    item.config.agent_session = item.config.test_agent.new_session(token)

    item.config.test_log_dir = lazy_mkdir(
        path=os.path.join(item.config.log_dir, item.name)
    )


def pytest_runtest_teardown(item: pytest.Item) -> None:
    pass


@pytest.fixture
def server(request):
    return request.config.server


@pytest.fixture
def agent(request):
    return request.config.agent_session


@pytest.fixture
def module_path(request):
    return request.config.module_path


@pytest.fixture
def log_dir(request):
    return request.config.test_log_dir()
