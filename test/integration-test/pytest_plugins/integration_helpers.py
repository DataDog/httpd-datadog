"""Pytest plugin for httpd-datadog integration tests.

This plugin provides:
- Environment variable fallback for command-line options
- Auto-build two module variants: with RUM and without RUM
- Automatic module selection based on test requirements
"""
import os
import subprocess
import sys
from pathlib import Path
import pytest


# Options are defined in conftest.py, no need to duplicate them here


def pytest_configure(config):
    """Register custom markers and initialize build state."""
    config.addinivalue_line(
        "markers",
        "requires_rum: test requires RUM support (DatadogRum directive available)"
    )

    # Initialize build state
    config._module_paths = {
        "rum": None,      # Path to RUM-enabled module
        "no_rum": None,   # Path to non-RUM module
    }
    config._built_variants = set()  # Track which variants have been built


def _build_module(project_root, variant="no_rum"):
    """Build a specific module variant.

    Args:
        project_root: Path to project root
        variant: "rum" or "no_rum"

    Returns:
        Path to built module
    """
    enable_rum = variant == "rum"
    build_dir_name = "build-rum" if enable_rum else "build"
    build_dir = project_root / build_dir_name

    variant_label = "with RUM" if enable_rum else "without RUM"
    print(f"\n🔨 Building module {variant_label}...")

    try:
        # Configure
        print(f"   Configuring CMake...")
        cmake_args = ["cmake", "-B", str(build_dir)]
        if enable_rum:
            cmake_args.append("-DHTTPD_DATADOG_ENABLE_RUM=ON")
        cmake_args.append(".")

        subprocess.run(
            cmake_args,
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True
        )

        # Build
        print(f"   Compiling...")
        subprocess.run(
            ["cmake", "--build", str(build_dir), "-j"],
            cwd=str(project_root),
            check=True,
            capture_output=True,
            text=True
        )

        # Verify module exists
        built_module = build_dir / "mod_datadog" / "mod_datadog.so"
        if not built_module.exists():
            raise FileNotFoundError(f"Built module not found at {built_module}")

        print(f"✓ Module built {variant_label}: {built_module}")
        return built_module

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed:")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        raise
    except Exception as e:
        print(f"\n✗ Build error: {e}")
        raise


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Build required module variants based on collected tests."""
    # Skip if user provided explicit module path
    if config.getoption("--module-path"):
        print("\n⚠️  Using user-provided module path (skipping auto-build)")
        return

    # Find project root
    test_dir = Path(__file__).parent.parent
    project_root = test_dir.parent.parent

    if not (project_root / "CMakeLists.txt").exists():
        pytest.exit("Cannot find project root CMakeLists.txt", returncode=1)

    # Determine which variants are needed
    has_rum_tests = any(item.get_closest_marker("requires_rum") for item in items)
    has_regular_tests = any(not item.get_closest_marker("requires_rum") for item in items)

    print(f"\n📦 Test variants needed: RUM={has_rum_tests}, Regular={has_regular_tests}")

    try:
        # Build variants on demand
        if has_rum_tests:
            config._module_paths["rum"] = _build_module(project_root, "rum")
            config._built_variants.add("rum")

        if has_regular_tests:
            config._module_paths["no_rum"] = _build_module(project_root, "no_rum")
            config._built_variants.add("no_rum")

    except Exception as e:
        pytest.exit(f"Failed to build required module variants: {e}", returncode=1)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    """Initialize module path based on collected tests."""
    # If user provided explicit path, use it
    explicit_path = session.config.getoption("--module-path")
    if explicit_path:
        session.config.module_path = explicit_path
        return

    # Otherwise, use the auto-built modules
    # Default to non-RUM module if both were built
    if session.config._module_paths.get("no_rum"):
        session.config.module_path = str(session.config._module_paths["no_rum"])
    elif session.config._module_paths.get("rum"):
        session.config.module_path = str(session.config._module_paths["rum"])
    else:
        pytest.exit("No module path available", returncode=1)


def pytest_runtest_setup(item):
    """Switch to appropriate module variant before each test."""
    # Skip if user provided explicit module path
    if item.config.getoption("--module-path"):
        return

    # Determine required variant
    requires_rum = item.get_closest_marker("requires_rum") is not None
    variant = "rum" if requires_rum else "no_rum"

    # Get the appropriate module path
    module_path = item.config._module_paths.get(variant)

    if not module_path:
        if requires_rum:
            pytest.fail(
                "RUM support required but RUM module was not built. "
                "This test needs @pytest.mark.requires_rum"
            )
        else:
            pytest.fail("Module not available for test")

    # Update the module path for this test
    item.config.module_path = str(module_path)
