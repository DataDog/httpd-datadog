import sys
import os
import pytest
import argparse
import subprocess
from contextlib import contextmanager

CWD = os.path.dirname(__file__)


@contextmanager
def setup_environment(module_path: str):
    # TODO: maybe make sure docker compose is not already up
    # TODO: retrieve all services and their host:port with docker inspect
    subprocess_args = {"shell": True, "cwd": CWD, "check": True, "capture_output": True}
    subprocess.run("docker compose up -d", **subprocess_args)
    subprocess.run(
        f"docker compose cp {module_path} httpd:/mod_ddtrace.so", **subprocess_args
    )

    try:
        yield
    finally:
        subprocess.run("docker compose down", **subprocess_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTPD integration tests")
    parser.add_argument("-k", help="Keyword filtering (forwarded to pytest)")
    parser.add_argument("--runtime-environment", choices=("docker", "local"))
    parser.add_argument(
        "--failfast", action="store_true", help="Stop after first failure"
    )
    parser.add_argument("module", help="mod_ddtrace.so to test")

    args = parser.parse_args()

    if not os.path.exists(args.module):
        print(f'HTTPD module "{args.module}" is missing')
        sys.exit(1)

    module_path = os.path.abspath(args.module)

    if args.runtime_environment == "local":
        print("local runtime environment is not supported yet")
        sys.exit(1)

    pytest_args = []
    if args.k:
        pytest_args.extend(["-k", args.k])
    if args.failfast:
        pytest_args.append("-x")

    test_directory = os.path.join(os.path.dirname(__file__), "scenarios")
    pytest_args.append(test_directory)

    with setup_environment(module_path):
        res = pytest.main(pytest_args)

    sys.exit(res)
