#!/usr/bin/env python3


def relpath(p: str) -> str:
    from pathlib import Path

    return Path(__file__).parent / p


@pytest.mark.skip(reason="Proxy fixture not implemented")
def test_propagation(server, proxy):
    def handle_req():
        # Except all mandatory headers to be found
        mandatory_headers = (
            "x-datadog-trace-id",
            "x-datadog-parent-id",
            "x-datadog-sampling-priority",
        )
        pass

    proxy.handle(
        "/",
    )
    assert server.load_configuration(relpath("conf/minimal.conf"))
    assert server.module_loaded("ddtrace_module")

    pass
