#!/usr/bin/env python3
import requests
import pytest


def relpath(p: str) -> str:
    from pathlib import Path

    return Path(__file__).parent / p


def test_default_configurations(server, agent):
    assert server.load_configuration(relpath("conf/minimal.conf"))
    assert server.module_loaded("ddtrace_module")

    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200

    traces = agent.get_traces(timeout=5)
    assert len(traces) >= 1

    trace = traces[0][0]
    assert trace["service"] == "httpd"
    assert trace["type"] == "server"


def test_directive_configurations(server, agent):
    assert server.load_configuration(relpath("conf/directives.conf"))
    assert server.module_loaded("ddtrace_module")

    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200

    traces = agent.get_traces(timeout=5)
    assert len(traces) >= 1

    trace = traces[0][0]
    assert trace["service"] == "integration-tests"
    assert trace["meta"]["env"] == "test"
    assert trace["meta"]["version"] == "1.0"


@pytest.mark.skip(reason="Restart service not implemented")
def test_env_var_configurations(server, agent):
    env = {
        "DD_SERVICE": "test_env_var_service",
        "DD_ENV": "test-env_var",
        "DD_VERSION": "1.2.3",
        "DD_TAGS": "foo:bar",
    }

    assert server.restart(conf=relpath("conf/minimal"), env=env)
    assert server.module_loaded("ddtrace_module")

    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200

    traces = agent.get_traces(timeout=2)
    assert len(traces) >= 1

    trace = traces[0]
    assert trace["service"] == "test_env_var_service"
    assert trace["meta"]["env"] == "test-env_var"
    assert trace["meta"]["version"] == "1.2.3"
    assert trace["meta"]["foo"] == "bar"
