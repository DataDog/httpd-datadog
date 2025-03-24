#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache 2.0 License. This product includes software developed at
# Datadog (https://www.datadoghq.com/).
#
# Copyright 2024-Present Datadog, Inc.

"""
This script collects and outputs licenses from third-party dependencies in CSV format.

It relies on the following dependencies:
   - cargo-license (<https://github.com/onur/cargo-license>)
   - get_licenses_copyrights (<https://github.com/DataDog/ospo-tools/tree/v0.2.0-beta>)

Usage:
======
# Clone the ospo-tools repository
# To print 3rd deps licenses
./scripts/license.py --licenses-script ~/dev/ospo-tools/src/ospo_tools/cli/get_licenses_copyrights.py

If what you are looking for is to add the license to the beginning of files, you can
use addlicense (https://github.com/google/addlicense). Example:

addlicense -f NOTICE -ignore "**/*.yml" .
"""

from license_tools import manual_mappings, ThirdParty, merge_dependencies
from typing import List
import csv
import sys
import glob
import subprocess
import json
import typing
import os
import argparse
import re

from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

def run_cmd(cmd: str) -> typing.Any:
    return subprocess.run(cmd, shell=True, capture_output=True, check=True)

def process_licenses(name: str, licenses: str) -> List[str]:
    if not licenses or licenses.upper() == "UNKNOWN":
        return []

    normalized = []

    for license in re.split(r';; | OR | AND |, ', licenses.translate(str.maketrans('', '', '"[]()\''))):
        normalized.append(license)

    return normalized


def process_copyright(copyright_str: str) -> List[str]:
    if not copyright_str or copyright_str.upper() == "UNKNOWN" or copyright_str.upper() == "NONE":
        return []
    split_values = re.split(r"\||', '", copyright_str)
    return [value.translate(str.maketrans('', '', '"[]()\'')) for value in split_values]

def cargo_licenses() -> typing.Dict[str, ThirdParty]:
    """
    Rely on `cargo-license`.
    """
    workspace_cargo = os.path.join(PROJECT_DIR, "Cargo.toml")
    r = run_cmd(
        f"cargo-license -j --manifest-path {workspace_cargo}",
    )
    j = json.loads(r.stdout)

    res = dict()
    for x in j:
        if x["name"] not in res:
            if x["license"] is not None:
                x["license"] = x["license"].translate(str.maketrans('', '', '"[]()\''))

            res[x["name"]] = ThirdParty(
                component=x["name"],
                origin=x["repository"],
                license=process_licenses(x["name"], x["license"]),
                copyright=process_copyright(x["authors"])
            )
    return res

def dd_licenses(script_path: str) -> typing.Dict[str, ThirdParty]:
    """
    Rely on `get_licenses_copyrights`.
    
    Args:
        script_path: Path to the get_licenses_copyrights.py script.
    """
    res = dict()
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Could not find script at {script_path}")

    r = run_cmd(f"python {script_path} https://github.com/DataDog/inject-browser-sdk")

    reader = csv.reader(r.stdout.decode().splitlines())
    next(reader)  # Skip header
    
    for row in reader:
        if not row:
            continue

        res[row[0]] = ThirdParty(
            component=row[0],
            origin=row[1],
            license=process_licenses(row[0], row[2]),
            copyright=process_copyright(row[3])
        )

    return res


def print_csv(deps: typing.Dict[str, ThirdParty]) -> None:
    print('"Component","Origin","License","Copyright"')
    for x in deps.values():
        print(f'"{x.component}","{x.origin}","{x.license}","{x.copyright}"')


def parse_args():
    parser = argparse.ArgumentParser(description="Collect and output licenses from third-party dependencies")
    parser.add_argument(
        "--licenses-script",
        required=True,
        help="Path to the get_licenses_copyrights.py"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    deps_licenses = dd_licenses(args.licenses_script)
    merge_dependencies(deps_licenses, cargo_licenses())
    deps_licenses.update(manual_mappings(deps_licenses))
    print_csv(deps_licenses)

    return 0


if __name__ == "__main__":
    sys.exit(main())
