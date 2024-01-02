#!/usr/bin/env python3
import os
import json
import requests
import pytest
import tempfile
from helper import relpath, make_configuration, save_configuration


def test_log_injection(server, agent, log_dir, module_path):
    """
    Verify trac parent ID and span ID can be used in custom log format to
    correlate Logs and Traces.
    """
    with tempfile.NamedTemporaryFile() as log:
        # Replace log path with log.name
        config = {
            "path": relpath("conf/log_injection.conf"),
            "var": {
                "log_file": log.name,
            },
        }

        conf_path = os.path.join(log_dir, "httpd.conf")
        save_configuration(make_configuration(config, log_dir, module_path), conf_path)

        assert server.check_configuration(conf_path)
        assert server.load_configuration(conf_path)
        r = requests.get(server.make_url("/"), timeout=2)
        assert r.status_code == 200
        server.stop(conf_path)

        traces = agent.get_traces(timeout=5)
        assert len(traces) == 1

        trace = traces[0][0]
        assert trace

        span_id = str(trace["span_id"])
        trace_id = "{high}{low}".format(
            high=trace["meta"]["_dd.p.tid"], low=hex(trace["trace_id"])[2:]
        )

        with open(log.name, "r") as f:
            for line in f:
                j = json.loads(line)
                assert j["trace_id"] == trace_id
                assert j["span_id"] == span_id
                break
