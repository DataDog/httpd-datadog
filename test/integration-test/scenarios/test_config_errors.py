"""Configuration errors must preserve their complete input as a C string."""

from pathlib import Path

import pytest

from helper import make_configuration, save_configuration


@pytest.mark.parametrize(
    "directive,value,detail",
    [
        ("DatadogAgentUrl", "x" * 400, "failed to parse"),
        ("DatadogSamplingRate", "x" * 400, "could not parse"),
        ("DatadogSamplingRate", "2." + "0" * 400, "expected range"),
        ("DatadogPropagationStyle", "x" * 400, "supported propagation style"),
    ],
    ids=["agent-url", "sampling-parse", "sampling-range", "propagation"],
)
def test_config_error_preserves_long_input(
    server, log_dir, module_path, directive, value, detail
):
    configuration = make_configuration(
        {"path": "conf/default.conf", "var": {}}, log_dir, module_path
    )
    configuration += f'\n{directive} "{value}"\n'
    conf_path = str(Path(log_dir) / "httpd.conf")
    save_configuration(configuration, conf_path)
    result = server._proc.run(f"-f {conf_path} -t")
    assert result.returncode == 1, result.stderr
    assert f'{directive}:'.encode() in result.stderr
    assert f'"{value}"'.encode() in result.stderr
    assert detail.encode() in result.stderr
