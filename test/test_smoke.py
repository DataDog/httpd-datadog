#!/usr/bin/env python3
import pytest
import shutil
import typing
import subprocess
from pathlib import Path
import requests


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
        )

    def copyfile(self, src: str, dst: str) -> bool:
        proc_res = subprocess.run(
            f"docker compose cp {src} {self._name}:{dst}",
            shell=True,
            check=True,
        )
        return proc_res.returncode == 0


class Server:
    def __init__(self, host, port, proc, conf) -> None:
        self.host = host
        self.port = port
        self._proc = proc
        self._conf = conf

    def load_configuration(self, conf_path: str) -> bool:
        if not self._proc.copyfile(conf_path, "/tmp-httpd.conf"):
            return False

        # TODO: use `with` statement
        # TODO: get stdout and check for syntax ok?
        if self._proc.run(f"apachectl -f /tmp-httpd.conf -t").returncode:
            return False

        self._proc.copyfile(conf_path, self._conf)
        return self._proc.run("apachectl -k restart").returncode == 0

    def is_module_loaded(self, module_name: str) -> bool:
        res = self._proc.run("apachectl -t -D DUMP_MODULES")
        if res.returncode != 0:
            return False

        for l in res.stdout.decode().split("\n"):
            if module_name in l:
                return True

        return False


def make_url(host: Server, path: str) -> str:
    url = f"http://{host.host}"
    if host.port:
        url += f":{host.port}"
    url += path if path else "/"

    return url


server = Server(
    host="localhost",
    port="8080",
    proc=DockerProc("httpd"),
    conf="/usr/local/apache2/conf/httpd.conf",
)

# Working:
# - docker compose up
# - docker compose cp mod_ddtrace.so httpd:/mod_ddtrace.so
# - pytest .

# TODO: have a main pytest
# - pass as param the .so and copy to docker container with
#   docker compose cp ../build/mod_ddtrace/mod_ddtrace.so  httpd:/
# - execution environment {"docker", "local"}
# for docker find host and port using docker inspect


def test_load_module():
    """
    Test the module can be loaded
    """
    assert server.load_configuration("conf/minimal.conf")
    assert server.is_module_loaded("ddtrace_module")


def test_minimal_config():
    assert server.load_configuration("conf/minimal.conf")

    r = requests.get(make_url(server, "/"), timeout=2)
    assert r.status_code == 200
    # assert agent.received_trace(timeout=10)
