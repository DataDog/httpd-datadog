#!/usr/bin/env python
import os
import urllib.request
import argparse
import sys
import tarfile
import tempfile

APR_URL = "https://dlcdn.apache.org/apr/"
DIST_URL = "https://archive.apache.org/dist/httpd"


def download(tar_url: str, working_dir: str) -> str:
    tar = tempfile.NamedTemporaryFile(delete=False)
    file_location, _ = urllib.request.urlretrieve(
        tar_url, os.path.join(working_dir, tar.name)
    )
    return file_location


def main():
    parser = argparse.ArgumentParser("Download HTTPD and dependencies source code")
    parser.add_argument(
        "-o", "--output", help="Directory where HTTPD will be extracted"
    )
    parser.add_argument("version", help="HTTPD version to download")

    args = parser.parse_args()

    apr_tar_url = f"{APR_URL}/apr-1.7.4.tar.gz"
    httpd_tar_url = f"{DIST_URL}/httpd-{args.version}.tar.gz"
    apr_util_tar_url = f"{APR_URL}/apr-util-1.6.3.tar.gz"

    httpd_src_dir = os.path.join(args.output)

    with tempfile.TemporaryDirectory(prefix="ddog") as workdir:
        print(f"Downloading HTTPD v{args.version} and its dependencies")

        apr_tar = download(apr_tar_url, workdir)
        apr_util_tar = download(apr_util_tar_url, workdir)
        httpd_tar = download(httpd_tar_url, workdir)

        print("Extracting...")
        with tarfile.open(httpd_tar) as tar:
            tar.extractall(args.output)

        srclib = os.path.join(args.output, f"httpd-{args.version}", "srclib")
        if not os.path.exists(srclib):
            print("Could not find srclib")
            return 1

        with tarfile.open(apr_tar) as tar:
            tar.extractall(srclib)
        with tarfile.open(apr_util_tar) as tar:
            tar.extractall(srclib)

    return 0


if __name__ == "__main__":
    sys.exit(main())
