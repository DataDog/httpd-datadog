"""Redirects and SSI subrequests must use the target's tracing config."""

import os
from typing import Any

import pytest
import requests

from conftest import AgentSession, Server
from helper import make_configuration, relpath, save_configuration


@pytest.mark.ci
@pytest.mark.parametrize(
    "path,status",
    [
        pytest.param("/missing", 404, id="redirect"),
        pytest.param("/include.shtml", 200, id="subrequest"),
    ],
)
@pytest.mark.parametrize(
    "enabled",
    [pytest.param(False, id="disabled"), pytest.param(True, id="enabled")],
)
def test_tracing_uses_target_config(
    server: Server,
    agent: AgentSession,
    log_dir: str,
    module_path: str,
    path: str,
    status: int,
    enabled: bool,
) -> None:
    config = {
        "path": relpath("conf/tracing_target.conf"),
        "var": {"target_tracing": "On" if enabled else "Off"},
    }
    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)
    response = requests.get(server.make_url(path), timeout=5)
    assert response.status_code == status
    assert response.text.strip() == "target body"
    assert server.stop(conf_path)

    check_target_spans(agent, path, enabled)


def check_target_spans(agent: AgentSession, path: str, enabled: bool) -> None:
    spans = [span for trace in agent.get_traces(timeout=5) for span in trace]
    roots = spans_for_path(spans, path)
    targets = spans_for_path(spans, "/target.html")
    assert len(roots) == 1, spans
    assert roots[0]["meta"]["scope"] == "source"
    if enabled:
        assert len(targets) == 1, spans
        assert targets[0]["meta"]["scope"] == "target"
        assert targets[0]["parent_id"] == roots[0]["span_id"]
    else:
        assert targets == [], spans


def spans_for_path(spans: list[dict[str, Any]], path: str) -> list[dict[str, Any]]:
    return [span for span in spans if span["resource"].split()[1] == path]
