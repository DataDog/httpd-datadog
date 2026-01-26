"""Pytest plugin for httpd-datadog integration tests.

This plugin provides:
- Environment variable fallback for command-line options
- Automatic RUM support detection
- Auto-skip for RUM tests when support unavailable
"""
import os
import pytest


def pytest_addoption(parser):
    """Add custom command-line options with environment variable fallback."""
    parser.addoption(
        "--bin-path",
        default=os.getenv("HTTPD_BIN_PATH"),
        help="Apache binary path (or set HTTPD_BIN_PATH env var)",
        type=str
    )
    parser.addoption(
        "--module-path",
        default=os.getenv("HTTPD_MODULE_PATH"),
        help="mod_datadog.so path (or set HTTPD_MODULE_PATH env var)",
        type=str
    )
    parser.addoption(
        "--log-dir",
        default=os.getenv("TEST_LOG_DIR"),
        help="Test log directory (or set TEST_LOG_DIR env var)",
        type=str
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_rum: test requires RUM support (DatadogRum directive available)"
    )


def pytest_sessionstart(session):
    """Detect if module has RUM support after server is initialized.

    This runs after conftest.py's pytest_sessionstart, so the server
    fixture is available.
    """
    try:
        module_path = session.config.getoption("--module-path")
        if not module_path:
            session.config.has_rum_support = False
            return

        server = session.config.server

        # Test if DatadogRum directive is recognized
        # The directive test will fail if RUM support is not compiled in
        has_rum = server.check_directive(
            f'LoadModule datadog_module {module_path} -C "DatadogRum On"'
        )

        session.config.has_rum_support = has_rum

        if has_rum:
            print(f"\n✓ RUM support detected in {module_path}")
        else:
            print(f"\n✗ RUM support NOT detected in {module_path}")
            print("  (Tests marked with @pytest.mark.requires_rum will be skipped)")

    except Exception as e:
        print(f"\n✗ Error detecting RUM support: {e}")
        session.config.has_rum_support = False


def pytest_runtest_setup(item):
    """Auto-skip tests requiring RUM if not available."""
    if item.get_closest_marker("requires_rum"):
        if not getattr(item.config, "has_rum_support", False):
            pytest.skip(
                "RUM support not available "
                "(module not compiled with -DHTTPD_DATADOG_ENABLE_RUM=ON)"
            )
