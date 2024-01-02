#!/usr/bin/env python3
import pytest

# import requests


def relpath(p: str) -> str:
    from pathlib import Path

    return Path(__file__).parent / p


@pytest.mark.smoke
def test_load_module(server):
    """
    Test the module can be loaded
    """
    assert server.load_configuration(relpath("conf/minimal.conf"))
    assert server.module_loaded("datadog_module")


# @pytest.mark.smoke
# def test_minimal_config(server, agent):
#     assert server.load_configuration(relpath("conf/minimal.conf"))
#     assert server.module_loaded("datadog_module")
#
#     r = requests.get(server.make_url("/"), timeout=2)
#     assert r.status_code == 200
#     assert agent.received_trace(timeout=10)
