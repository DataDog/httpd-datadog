"""Configuration errors must preserve their complete input as a C string."""

from pathlib import Path

import pytest

from helper import make_configuration, save_configuration


@pytest.mark.ci
@pytest.mark.parametrize(
    "directive,value,error",
    [
        ("DatadogAgentUrl", "x" * 400, 'failed to parse "{value}" URL'),
        ("DatadogSamplingRate", "x" * 400, 'could not parse "{value}" input'),
        (
            "DatadogSamplingRate", "2." + "0" * 400,
            '"{value}" input is not in the [0;1] expected range',
        ),
        (
            "DatadogPropagationStyle", "x" * 400,
            '"{value}" is not a supported propagation style. Only "datadog", '
            '"tracecontext" and "b3" are valid propagation styles',
        ),
    ],
    ids=["agent-url", "sampling-parse", "sampling-range", "propagation"],
)
def test_config_error_preserves_long_input(
    server, log_dir, module_path, directive, value, error
):
    configuration = make_configuration(
        {"path": "conf/default.conf", "var": {}}, log_dir, module_path
    )
    configuration += f'\n{directive} "{value}"\n'
    conf_path = str(Path(log_dir) / "httpd.conf")
    save_configuration(configuration, conf_path)
    result = server._proc.run(f"-f {conf_path} -t")
    assert result.returncode == 1, result.stderr
    expected_error = f"{directive}: {error.format(value=value)}".encode()
    assert expected_error in result.stderr.splitlines(), result.stderr
