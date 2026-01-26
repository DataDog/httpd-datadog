"""Pytest plugin for httpd-datadog integration tests.

This plugin provides:
- Environment variable fallback for command-line options
- Auto-build module with RUM when RUM tests detected
- Automatic RUM support detection
"""
import os
import subprocess
import sys
from pathlib import Path
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


def pytest_collection_modifyitems(config, items):
    """Build module with RUM if RUM tests are collected."""
    # Check if any RUM tests were collected
    has_rum_tests = any(item.get_closest_marker("requires_rum") for item in items)

    if not has_rum_tests:
        return

    print(f"\n🔨 RUM tests detected - building module with RUM support...")

    # Find project root (where CMakeLists.txt is)
    test_dir = Path(__file__).parent.parent
    project_root = test_dir.parent.parent

    if not (project_root / "CMakeLists.txt").exists():
        pytest.exit("Cannot find project root CMakeLists.txt", returncode=1)

    build_dir = project_root / "build"

    # Build with RUM enabled
    try:
        # Configure with RUM enabled
        print(f"   Configuring CMake with RUM enabled...")
        subprocess.run(
            ["cmake", "-B", str(build_dir), "-DHTTPD_DATADOG_ENABLE_RUM=ON", "."],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True
        )

        # Build
        print(f"   Building module...")
        subprocess.run(
            ["cmake", "--build", str(build_dir), "-j"],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True
        )

        # Update module path to point to built module
        built_module = build_dir / "mod_datadog" / "mod_datadog.so"
        if not built_module.exists():
            pytest.exit(f"Built module not found at {built_module}", returncode=1)

        # Override module path in config
        config.option.module_path = str(built_module)
        os.environ["HTTPD_MODULE_PATH"] = str(built_module)

        print(f"✓ Module built with RUM support: {built_module}")

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed:")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        pytest.exit("Failed to build module with RUM support", returncode=1)


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
        has_rum = server.check_directive(
            f'LoadModule datadog_module {module_path} -C "DatadogRum On"'
        )

        session.config.has_rum_support = has_rum

        if has_rum:
            print(f"\n✓ RUM support detected in {module_path}")
        else:
            print(f"\n✗ RUM support NOT detected in {module_path}")
            print("  (RUM tests will fail)")

    except Exception as e:
        print(f"\n✗ Error detecting RUM support: {e}")
        session.config.has_rum_support = False


def pytest_runtest_setup(item):
    """Fail tests requiring RUM if not available."""
    if item.get_closest_marker("requires_rum"):
        if not getattr(item.config, "has_rum_support", False):
            pytest.fail(
                "RUM support not available - build failed or module not compiled with -DHTTPD_DATADOG_ENABLE_RUM=ON"
            )
