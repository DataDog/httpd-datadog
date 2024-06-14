#!/usr/bin/env python
import os
import shutil
import argparse
import sys
import tempfile
import subprocess


def download_http_source(version: str, output_dir: str, verbose: bool) -> bool:
    print(f"""Installing Apache HTTP Server v{version} source to {output_dir}""")
    pipe = subprocess.STDOUT if verbose else subprocess.DEVNULL
    with tempfile.TemporaryDirectory() as dir:
        cmds = [
            {
                "args": f"git clone --branch {version} --depth 1 https://github.com/apache/httpd.git",
                "cwd": dir,
                "shell": True,
                "stdout": pipe,
                "stderr": pipe,
            },
            {
                "args": "git clone --branch 1.7.4 --depth 1 https://github.com/apache/apr.git",
                "cwd": os.path.join(dir, "httpd", "srclib"),
                "shell": True,
                "stdout": pipe,
                "stderr": pipe,
            },
            {
                "args": "git clone --branch 1.6.3 --depth 1 https://github.com/apache/apr-util.git",
                "cwd": os.path.join(dir, "httpd", "srclib"),
                "shell": True,
                "stdout": pipe,
                "stderr": pipe,
            },
        ]
        for cmd in cmds:
            if verbose:
                print(f"cmd: {cmd['args']}")
            else:
                cmd_args = cmd["args"]
                last_slash = cmd_args.rfind("/") + 1
                repo = cmd_args[last_slash:-4]
                print(f" - Downloading {repo}...")

            if not subprocess.run(**cmd):
                return False

        shutil.move(dir, output_dir)
    return True


def main():
    parser = argparse.ArgumentParser("Download Apache HTTP Server and its dependencies")
    parser.add_argument(
        "-v", "--verbose", help="Increase verbosity level", default=False
    )
    parser.add_argument(
        "-o", "--output", help="Directory where HTTPD will be extracted"
    )
    parser.add_argument("version", help="HTTPD version to download")

    args = parser.parse_args()

    if not subprocess.run("git -v", shell=True, stdout=subprocess.DEVNULL):
        print("git command must be available")
        return 1

    if not download_http_source(args.version, args.output, args.verbose):
        print("Failed to download Apache HTTP Server")
        return 1

    pipe = subprocess.STDOUT if args.verbose else subprocess.DEVNULL
    if not subprocess.run(
        "./buildconf", cwd=os.path.join(args.output, "httpd"), stdout=pipe, stderr=pipe
    ):
        print("Error while configuring Apache HTTP Server")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
