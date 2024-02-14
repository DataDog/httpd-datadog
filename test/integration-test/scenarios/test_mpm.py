#!/usr/bin/env python3
import pytest


def relpath(p: str) -> str:
    from pathlib import Path

    return Path(__file__).parent / p


@pytest.mark.skip(reason="Changing MPM module requires to restart the service")
def test_prefork_mpm(server):
    import pdb

    pdb.set_trace()
    assert server.load_configuration(relpath("conf/prefork_mpm.conf"))
    assert server.is_module_loaded("ddtrace_module")
