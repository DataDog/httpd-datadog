#!/usr/bin/env python3
import os
import requests
import pytest
from helper import (
    relpath,
    make_configuration,
    save_configuration,
    make_temporary_configuration,
)


def test_default_configurations(server, agent, log_dir, module_path):
    config = {
        "path": relpath("conf/default.conf"),
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200

    assert server.stop(conf_path)

    traces = agent.get_traces(timeout=5)
    assert len(traces) >= 1

    trace = traces[0][0]
    assert trace["service"] == "httpd"
    assert trace["type"] == "server"


def test_directive_configurations(server, agent, log_dir, module_path):
    config = {
        "path": relpath("conf/directives.conf"),
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200

    assert server.stop(conf_path)

    traces = agent.get_traces(timeout=5)
    assert len(traces) == 1

    trace = traces[0][0]
    assert trace["service"] == "integration-tests"
    assert trace["meta"]["env"] == "test"
    assert trace["meta"]["version"] == "1.0"
    assert trace["meta"]["foo"] == "bar"


@pytest.mark.skip(reason="Restart service not implemented")
def test_env_var_configurations(server, agent):
    """
    Verify datadog's environment variables can be consumed by the tracer embedded in the httpd.
    """
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
    assert len(traces) == 1

    trace = traces[0]
    assert trace["service"] == "test_env_var_service"
    assert trace["meta"]["env"] == "test-env_var"
    assert trace["meta"]["version"] == "1.2.3"
    assert trace["meta"]["foo"] == "bar"


def test_datadog_tag_merge(server, agent, log_dir, module_path):
    config = {
        "path": relpath("conf/directives.conf"),
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    r = requests.get(server.make_url("/merge"), timeout=2)
    assert r.status_code == 200

    r = requests.get(server.make_url("/merge/level-2"), timeout=2)
    assert r.status_code == 200

    assert server.stop(conf_path)

    traces = agent.get_traces(timeout=5)
    assert len(traces) == 2

    for trace in traces:
        root_span = trace[0]
        assert root_span["meta"]["foo"] == "bar"
        assert root_span["meta"]["level-1"] == "yes"
        if "level-2" in root_span["resource"]:
            assert "level-2" in root_span["meta"]
        else:
            assert "level-2" not in root_span["meta"]


@pytest.mark.ci
@pytest.mark.parametrize(
    "test_input",
    [
        {"value": 100, "expected_status": False},
        {"value": 1, "expected_status": True},
        {"value": 1.0, "expected_status": True},
        {"value": 0.0, "expected_status": True},
        {"value": 0, "expected_status": True},
        {"value": "not a digit", "expected_status": False},
    ],
)
def test_datadog_sampling_rate_input(server, module_path, test_input):
    """
    Verify only values between [0;1] are accepted.

    TODO: Use random values generator.
    """
    config = {
        "path": relpath("conf/sampling_rate.conf"),
        "var": {"sampling_rate_value": test_input["value"]},
    }

    with make_temporary_configuration(config, module_path) as conf_path:
        assert server.check_configuration(conf_path) == test_input["expected_status"]


@pytest.mark.ci
@pytest.mark.parametrize(
    "test_input",
    [
        {"value": "datadog", "expected_status": True},
        {"value": "dAtaDOg", "expected_status": True},
        {"value": "tracecontext", "expected_status": True},
        {"value": "b3", "expected_status": True},
        {"value": "datadog tracecontext b3", "expected_status": True},
        {"value": "Hello Mars", "expected_status": False},
    ],
)
def test_datadog_propagation_style_input(server, module_path, test_input):
    """
    Verify only a set of values are accepted by `DatadogPropagationStyle`.
    """
    config = {
        "path": relpath("conf/propagation_style.conf"),
        "var": {"propagation_style_value": test_input["value"]},
    }

    with make_temporary_configuration(config, module_path) as conf_path:
        assert server.check_configuration(conf_path) == test_input["expected_status"]


@pytest.mark.ci
@pytest.mark.parametrize(
    "test_input",
    [
        {"value": "http://localhost:8126", "expected_status": True},
        {"value": "unix://localhost:8126", "expected_status": True},
        {"value": "localhost:8126", "expected_status": False},  # < Missing scheme
    ],
)
def test_datadog_agent_url_input(server, module_path, test_input):
    """
    Verify only valid URIs are accepted by `DatadogAgentUrl`.
    """
    config = {
        "path": relpath("conf/agent_url.conf"),
        "var": {"propagation_style_value": test_input["value"]},
    }

    with make_temporary_configuration(config, module_path) as conf_path:
        assert server.check_configuration(conf_path) == test_input["expected_status"]


def test_trust_inbound_span_directive(server, agent, log_dir, module_path):
    """
    Verify `DatadogTrustInboundSpan` directive create a parent-child relationship
    depending of the value.

    If `On` and the request has a valid trace context, then the httpd span should be
    the child of the inbound span.

    Else, the httpd span should be the root span.
    """
    config = {
        "path": relpath("conf/directives.conf"),
        "var": {},
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)

    trace_context = {
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "tracestate": "dd=s:2;o:rum;p:00f067aa0ba902b7;t.dm:-5",
    }
    r = requests.get(server.make_url("/trust-upstream-span"), headers=trace_context)
    assert r.status_code == 200

    r = requests.get(server.make_url("/ignore-upstream-span"), headers=trace_context)
    assert r.status_code == 200

    assert server.stop(conf_path)

    traces = agent.get_traces(timeout=2)
    assert len(traces) == 2

    for trace in traces:
        root_span = trace[0]
        trust_inbound_tag = root_span["meta"].get("trust-inbound-span", None)
        assert trust_inbound_tag

        if trust_inbound_tag == "true":
            assert root_span["parent_id"] == 67667974448284343
        else:
            assert root_span["parent_id"] == 0
