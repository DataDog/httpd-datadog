#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache 2.0 License. This product includes software developed at
# Datadog (https://www.datadoghq.com/).
#
# Copyright 2024-Present Datadog, Inc.
"""
Install dependencies for cross-compilation.

Usage:
======
./install-xwin-toolchain.py --output-dir /xwin
"""
import argparse
import typing
import subprocess
import sys
import platform
import tempfile
import tarfile
import urllib.request
import shutil
import hashlib
from pathlib import Path

XWIN_VERSION = "0.6.5"


def download_file(url: str, destination: Path) -> Path:
    print(f"Downloading {url} to {destination}")
    response = urllib.request.urlopen(url)
    with open(destination, "wb") as output:
        shutil.copyfileobj(response, output)

    assert destination.exists()
    return destination


def read_content_file(p: Path) -> str:
    with open(p, "r") as f:
        return f.readlines()[0].strip()


def sha256(filename: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def build_url(os: str, arch: str, xwin_version: str) -> tuple[str, str]:
    normalize_arch = {
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "amd64": "x86_64",
        "x86_64": "x86_64",
    }

    normalize_os = {
        "Linux": "unknown-linux-musl",
        "Darwin": "apple-darwin",
        "Windows": "pc-windows-msvc",
    }

    final_os = normalize_os.get(os, None)
    final_arch = normalize_arch.get(arch, None)

    assert final_os
    assert final_arch

    targz = f"https://github.com/Jake-Shadle/xwin/releases/download/{xwin_version}/xwin-{xwin_version}-{final_arch}-{final_os}.tar.gz"
    sign = targz + ".sha256"
    return targz, sign


def find_bin_location(root: Path, bin: str) -> typing.Optional[Path]:
    for p in root.glob(f"**/{bin}"):
        return root.joinpath(p)

    return None


def run(cmd: str) -> int:
    print(f"Running {cmd}")
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        text=True,  # This allows us to read the output as strings
    )

    if process.stdout:
        for line in iter(process.stdout.readline, ""):
            sys.stdout.write(line)

    process.wait()
    return process.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Install windows toolchain")
    parser.add_argument(
        "--xwin-version",
        help=f"xwin version to download. Default to {XWIN_VERSION}",
        default=XWIN_VERSION,
    )
    parser.add_argument(
        "--skip-verification", help="Skip signature verification", action="store_true"
    )
    parser.add_argument(
        "--output-dir", help="Location where the toolchain will be installed"
    )
    args = parser.parse_args()

    os = platform.system()
    arch = platform.machine()

    artifact_url, signature_url = build_url(os, arch, args.xwin_version)

    with tempfile.TemporaryDirectory() as work_dir:
        p_work_dir = Path(work_dir)
        xwin_tgz = download_file(artifact_url, p_work_dir.joinpath("xwin.tar.gz"))

        if not args.skip_verification:
            xwin_sign = download_file(signature_url, p_work_dir.joinpath("xwin.sha256"))

            expected_sha256 = read_content_file(xwin_sign)
            computed_sha256 = sha256(xwin_tgz)
            if expected_sha256 != computed_sha256:
                print(
                    f"sha256 verification failed. expected={expected_sha256}, computed={computed_sha256}"
                )
                return 1

        with tarfile.open(xwin_tgz) as tar:
            tar.extractall(path=work_dir)

        xwin_bin = find_bin_location(p_work_dir, "xwin")
        if not xwin_bin:
            print(f'Could not find "{xwin_bin}" binary in {p_work_dir}')
            return 1

        cmd = f"{xwin_bin} --accept-license splat --include-debug-libs --include-debug-symbols --output {args.output_dir}"
        rc = run(cmd)
        return rc


if __name__ == "__main__":
    sys.exit(main())
