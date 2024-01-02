#!/usr/bin/env python3
import os
import pytest
import requests
from helper import relpath, make_configuration, save_configuration


@pytest.mark.smoke
def test_load_module(server, module_path):
    """
    Test the module can be loaded
    """
    assert server.check_directive(f"LoadModule datadog_module {module_path}")


@pytest.mark.smoke
@pytest.mark.parametrize("mpm", ["prefork", "worker"])
def test_mpm(mpm, server, agent, log_dir, module_path):
    """
    Verify all official Multi-Processing Modules (MPM) are supported and generate
    traces.

    NOTE: httpd must be build with `--enable-mpms-shared="prefork worker event"`.
    NOTE: temporarily disabled event because it does not work in docker.
    """
    mpm_module_directives = {
        "prefork": "LoadModule mpm_prefork_module modules/mod_mpm_prefork.so",
        "worker": "LoadModule mpm_worker_module  modules/mod_mpm_worker.so",
        "event": "LoadModule mpm_event_module   modules/mod_mpm_event.so",
    }

    assert mpm in mpm_module_directives

    config = {
        "path": relpath("conf/mpm.conf"),
        "var": {
            "load_mpm_module": mpm_module_directives[mpm],
        },
    }

    conf_path = os.path.join(log_dir, "httpd.conf")
    save_configuration(make_configuration(config, log_dir, module_path), conf_path)

    assert server.check_configuration(conf_path)
    assert server.load_configuration(conf_path)
    r = requests.get(server.make_url("/"), timeout=2)
    assert r.status_code == 200
    assert agent.received_trace(timeout=10)
    assert server.stop(conf_path)
