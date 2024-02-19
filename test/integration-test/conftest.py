import subprocess
import os
import typing
import time
import uuid

import requests
from datetime import datetime
import pytest

CWD = os.path.dirname(__file__)
CWD_DOCKER_COMPOSE = CWD


class DockerProc:
    def __init__(self, container_name: str) -> None:
        self._name = container_name

    # TODO: Fix typing
    def run(self, cmd: str) -> typing.Any:
        return subprocess.run(
            f"docker compose exec {self._name} {cmd}",
            shell=True,
            check=True,
            capture_output=True,
            cwd=CWD_DOCKER_COMPOSE,
        )

    def copyfile(self, src: str, dst: str) -> bool:
        proc_res = subprocess.run(
            f"docker compose cp {src} {self._name}:{dst}",
            shell=True,
            check=True,
            cwd=CWD_DOCKER_COMPOSE,
        )
        return proc_res.returncode == 0


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

    def load_configuration(self, conf_path: str) -> bool:
        if not os.path.exists(conf_path):
            raise Exception(f"Configuration not found: {conf_path}")

        if not self._proc.copyfile(conf_path, "/tmp-httpd.conf"):
            return False

        # TODO: use `with` statement
        # TODO: get stdout and check for syntax ok?
        if self._proc.run(f"apachectl -f /tmp-httpd.conf -t").returncode:
            return False

        self._proc.copyfile(conf_path, self._conf)
        return self._proc.run("apachectl -k restart").returncode == 0

    def module_loaded(self, module_name: str) -> bool:
        res = self._proc.run("apachectl -t -D DUMP_MODULES")
        if res.returncode != 0:
            return False

        for l in res.stdout.decode().split("\n"):
            if module_name in l:
                return True

        return False


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
                print(f"Received: {r.json()}")
                return r.json()

            time.sleep(1)

        return []


class Agent:
    def __init__(self, host, port, proc) -> None:
        self.host = host
        self.port = port
        self._proc = proc

    def new_session(self, token=None) -> AgentSession:
        if token is None:
            token = str(uuid.uuid4())

        r = requests.get(
            f"http://{self.host}:{self.port}/test/session/start?test_session_token={token}"
        )
        r.raise_for_status()

        return AgentSession(self, token)


def pytest_addoption(parser, pluginmanager) -> None:
    """
    Allows plugins and conftest files to perform initial configuration.
    This hook is called for every plugin and initial conftest
    file after command line options have been parsed.
    """
    parser.addoption("--runtime-environment", choices=("docker", "local"))
    parser.addoption("--module-path", help="mod_ddtrace.so under test", required=True)


def pytest_configure(config):
    """
    This hook is called for every plugin and initial conftest file after command line options have been parsed
    """
    # Register custom markers
    config.addinivalue_line("markers", "smoke: marks tests as smoke tests")


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    """
    module_path = os.path.abspath(session.config.getoption("--module-path"))

    # TODO: maybe make sure docker compose is not already up
    # TODO: retrieve all services and their host:port with docker inspect
    subprocess_args = {"shell": True, "cwd": CWD, "check": True, "capture_output": True}
    subprocess.run("docker compose up -d", **subprocess_args)
    subprocess.run(
        f"docker compose cp {module_path} httpd:/mod_ddtrace.so", **subprocess_args
    )

    session.config.server = Server(
        host="localhost",
        port="8080",
        proc=DockerProc("httpd"),
        conf="/usr/local/apache2/conf/httpd.conf",
    )

    session.config.agent = Agent(
        host="localhost",
        port="8136",
        proc=DockerProc("agent"),
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus) -> None:
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    subprocess_args = {"shell": True, "cwd": CWD, "check": True, "capture_output": True}
    subprocess.run("docker compose down", **subprocess_args)


def pytest_runtest_setup(item: pytest.Item) -> None:
    # TODO: start a new session on agent
    # called for running each test in 'a' directory
    token = f"{item.name}-{uuid.uuid4()}"
    item.config.agent_session = item.config.agent.new_session(token)


def pytest_runtest_teardown(item: pytest.Item) -> None:
    # TODO: call </test/session/clear>
    pass


@pytest.fixture
def server(request):
    return request.config.server


@pytest.fixture
def agent(request):
    return request.config.agent_session
