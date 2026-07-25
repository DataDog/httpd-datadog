pytest_plugins = ["pytest_plugins.integration_helpers"]

import argparse
import asyncio
import inspect
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import typing
import uuid
from datetime import datetime

import pytest
import requests
from aiohttp import web
from ddapm_test_agent.agent import make_app

CWD = os.path.dirname(__file__)

# CI runners pre-set DD_*; strip them, so per-test settings take precedence.
for _dd_var in ("DD_SERVICE", "DD_ENV", "DD_VERSION"):
    os.environ.pop(_dd_var, None)


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
            print("[error] Configuration check failed:")
            print(f"[error] stdout: {result.stdout.decode('utf-8')}")
            print(f"[error] stderr: {result.stderr.decode('utf-8')}")
        return result.returncode == 0

    def wait_until_ready(self, conf_path: str, timeout: float = 5.0) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.create_connection((self.host, int(self.port)), timeout=0.5):
                    print(
                        f"[debug] Apache accepting connections on {self.host}:{self.port}"
                    )
                    return True
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

        print(f"[error] Apache failed to respond after {timeout} seconds")
        error_log = os.path.join(os.path.dirname(conf_path), "error_log")
        if os.path.exists(error_log):
            try:
                with open(error_log) as log:
                    if error_content := log.read():
                        print("[error] Error log content:")
                        print(error_content[-1000:])
            except OSError as error:
                print(f"[error] Could not read error log: {error}")
        return False

    def load_configuration(self, conf_path: str) -> bool:
        if not os.path.exists(conf_path):
            raise Exception(f"Configuration not found: {conf_path}")

        # Stop leftovers before starting Apache.
        self._proc.run(f"-f {conf_path} -k stop")
        time.sleep(0.5)

        result = self._proc.run(f"-f {conf_path} -k start")
        if result.returncode != 0:
            print(
                f"[error] Apache start command failed with exit code {result.returncode}:"
            )
            print(f"[error] stdout: {result.stdout.decode('utf-8')}")
            print(f"[error] stderr: {result.stderr.decode('utf-8')}")
            # apachectl can fail even when Apache starts; probe below.

        # A TCP probe avoids creating a traced HTTP request.
        return self.wait_until_ready(conf_path)

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
        self.host = host
        self.port = port
        self._ready = threading.Event()
        self._thread: typing.Optional[threading.Thread] = None
        self._loop: typing.Optional[asyncio.AbstractEventLoop] = None
        self._stop: typing.Optional[asyncio.Event] = None
        self._error: typing.Optional[BaseException] = None
        make_app_kwargs = dict(
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
            vcr_json_body_normalizers="",
            vcr_body_regex_normalizers="",
            dd_site="",
            dd_api_key="",
            disable_llmobs_data_forwarding=False,
        )
        # Added in ddapm-test-agent 1.64.1. GitHub's smoke-test image can carry
        # an older compatible agent, so only pass it when that API supports it.
        if "vcr_body_regex_normalizers" in inspect.signature(make_app).parameters:
            make_app_kwargs["vcr_body_regex_normalizers"] = ""
        self._app = make_app(**make_app_kwargs)

    def internal_run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop = asyncio.Event()
        runner = web.AppRunner(self._app)
        try:
            self._loop.run_until_complete(runner.setup())
            # Bound aiohttp's default 60s keep-alive shutdown.
            site = web.TCPSite(runner, self.host, self.port, shutdown_timeout=1.0)
            self._loop.run_until_complete(site.start())
            self._ready.set()
            self._loop.run_until_complete(self._stop.wait())
        except Exception as error:
            self._error = error
        finally:
            self._ready.set()
            try:
                self._loop.run_until_complete(runner.cleanup())
            except Exception as error:
                if self._error is None:
                    self._error = error
            self._loop.close()

    def run(self) -> None:
        # A stuck aiohttp loop must not block interpreter shutdown.
        self._thread = threading.Thread(target=self.internal_run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("test agent did not become ready within 5 seconds")
        if self._error is not None:
            raise RuntimeError("test agent failed to start") from self._error

    def stop(self) -> None:
        if self._thread is None or self._loop is None or self._stop is None:
            return
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=3.0)
        if self._thread.is_alive():
            raise RuntimeError("test agent did not stop within 3 seconds")
        if self._error is not None:
            raise RuntimeError("test agent failed") from self._error

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
    if not hasattr(session.config, "module_path") or session.config.module_path is None:
        session.config.module_path = session.config.getoption("--module-path")

    apachectl_bin = session.config.getoption("--bin-path")

    log_dir = session.config.getoption("--log-dir")
    if log_dir:
        log_dir = os.path.abspath(log_dir)
        if os.path.exists(log_dir):
            # TODO: Warn old logs will be removed and manage error
            shutil.rmtree(log_dir)
        os.mkdir(log_dir)
    else:
        log_dir = tempfile.mkdtemp(prefix="log-httpd-tests-")

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
