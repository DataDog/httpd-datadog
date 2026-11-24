#!/usr/bin/env python3
"""Release mod_datadog from the GitLab pipeline of a version tag.

Usage:
    scripts/release.py --version-tag v1.2.3 [--pipeline-id ID] [--local-user KEYID]
    scripts/release.py --version-tag v1.2.3 --pipeline-id ID --dry-run --out-dir DIR
    scripts/release.py --version-tag v1.2.3 --publish

By default, the script downloads the module builds of the pipeline, zips them,
signs each zip with GPG and creates a draft release with `gh`.

--publish (after the smoke tests) runs the manual promote-s3-latest job, then
publishes the draft release.

GitLab token: GITLAB_TOKEN, or `ddtool auth gitlab token`.
"""

import argparse
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

GITLAB_API = "https://gitlab.ddbuild.io/api/v4"
GITLAB_PROJECT = quote("DataDog/httpd-datadog", safe="")
GITHUB_REPO = "DataDog/httpd-datadog"

# Release asset prefix -> GitLab build job. All builds store the module in
# artifacts/<arch>/.
ASSETS = {
    "mod_datadog_artifact": ("build:amd64:no-rum", "amd64"),
    "mod_datadog-amd64": ("build:amd64", "amd64"),
    "mod_datadog-arm64": ("build:arm64", "arm64"),
}


def run(command, **kwargs):
    print("+", shlex.join(str(arg) for arg in command), file=sys.stderr)
    return subprocess.run([str(arg) for arg in command], check=True, **kwargs)


def gitlab_token() -> str:
    if token := os.environ.get("GITLAB_TOKEN"):
        return token
    result = run(["ddtool", "auth", "gitlab", "token"], capture_output=True, text=True)
    if not result.stdout.strip():
        raise SystemExit(f"No GitLab token from ddtool:\n{result.stderr}")
    return result.stdout.strip().splitlines()[-1]


def gitlab_get(path: str, token: str, method: str = "GET") -> bytes:
    url = f"{GITLAB_API}/projects/{GITLAB_PROJECT}{path}"
    print(f"+ {method}", url, file=sys.stderr)
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}, method=method
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        raise SystemExit(f"GitLab API error {error.code} for {url}: {body}") from error


def find_pipeline(tag: str, token: str) -> int:
    pipelines = json.loads(
        gitlab_get(f"/pipelines?ref={quote(tag, safe='')}&per_page=1", token)
    )
    if not pipelines:
        raise SystemExit(f"No pipeline found for tag {tag}.")
    return pipelines[0]["id"]


def pipeline_jobs(pipeline_id: int, token: str) -> dict[str, dict]:
    jobs = {}
    page = 1
    while page_jobs := json.loads(
        gitlab_get(f"/pipelines/{pipeline_id}/jobs?per_page=100&page={page}", token)
    ):
        jobs.update((job["name"], job) for job in page_jobs)
        page += 1

    failed = [
        name
        for name, job in jobs.items()
        if job["status"] not in ("success", "manual", "skipped", "created")
        and not job["allow_failure"]
    ]
    if failed:
        raise SystemExit(
            f"Pipeline {pipeline_id} has unsuccessful jobs: {', '.join(failed)}"
        )
    return jobs


def write_zip(path: Path, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    # Without it, unzip creates the file with mode 0600.
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    with zipfile.ZipFile(path, "w") as out:
        out.writestr(info, data)


def prepare_assets(jobs: dict[str, dict], token: str, out_dir: Path) -> list[Path]:
    assets = []
    for prefix, (job_name, arch) in ASSETS.items():
        job = jobs.get(job_name)
        if job is None or job["status"] != "success":
            raise SystemExit(f"Job {job_name} is missing or did not succeed.")
        for suffix, name in (
            ("", "mod_datadog.so"),
            ("-debug", "mod_datadog.so.debug"),
        ):
            data = gitlab_get(
                f"/jobs/{job['id']}/artifacts/artifacts/{arch}/{name}", token
            )
            asset = out_dir / f"{prefix}{suffix}.zip"
            write_zip(asset, name, data)
            assets.append(asset)
    return assets


def publish(tag: str, jobs: dict[str, dict], token: str, dry_run: bool) -> None:
    view = ["gh", "release", "view", tag, "--repo", GITHUB_REPO]
    if subprocess.run(view, stdout=subprocess.DEVNULL).returncode != 0:
        raise SystemExit(f"No GitHub release for {tag}. Create the draft first.")
    job = jobs.get("promote-s3-latest")
    if job is None:
        raise SystemExit("Job promote-s3-latest not found.")
    publish_command = ["gh", "release", "edit", tag, "--draft=false", "--repo", GITHUB_REPO]  # fmt: skip
    if dry_run:
        print(
            f"Dry run, not playing promote-s3-latest ({job['status']}): {job['web_url']}"
        )
        print("Dry run, not running:", shlex.join(publish_command))
        return

    if job["status"] == "manual":
        gitlab_get(f"/jobs/{job['id']}/play", token, method="POST")
    print(f"Waiting for promote-s3-latest: {job['web_url']}")
    while (
        status := json.loads(gitlab_get(f"/jobs/{job['id']}", token))["status"]
    ) != "success":
        if status in ("failed", "canceled", "skipped"):
            raise SystemExit(
                f"promote-s3-latest is {status}. Retry it in GitLab, then run --publish again."
            )
        time.sleep(10)
    run(publish_command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--version-tag", required=True, help="Version tag, for example v1.2.3."
    )
    parser.add_argument(
        "--pipeline-id",
        type=int,
        help="GitLab pipeline ID. Default: latest pipeline of the tag.",
    )
    parser.add_argument(
        "--local-user",
        help="GPG key used to sign the assets. Default: gpg default key.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the release commands, but do not run them.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="After the smoke tests: update S3 latest, then publish the draft.",
    )
    parser.add_argument(
        "--out-dir", type=Path, help="Keep the assets in this directory."
    )
    args = parser.parse_args()

    token = gitlab_token()
    pipeline_id = args.pipeline_id or find_pipeline(args.version_tag, token)
    print(
        f"Pipeline: https://gitlab.ddbuild.io/DataDog/httpd-datadog/-/pipelines/{pipeline_id}"
    )
    ref = json.loads(gitlab_get(f"/pipelines/{pipeline_id}", token))["ref"]
    if ref != args.version_tag:
        if not args.dry_run:
            raise SystemExit(
                f"Pipeline {pipeline_id} is for {ref}, not {args.version_tag}."
            )
        print(f"Warning: pipeline {pipeline_id} is for {ref}, not {args.version_tag}.")
    jobs = pipeline_jobs(pipeline_id, token)

    if args.publish:
        publish(args.version_tag, jobs, token, args.dry_run)
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = args.out_dir or Path(tmp)
        out_dir.mkdir(parents=True, exist_ok=True)
        assets = prepare_assets(jobs, token, out_dir)

        gpg = ["gpg", "--yes", "--armor", "--detach-sign"]
        if args.local_user:
            gpg += ["--local-user", args.local_user]
        signatures = []
        for asset in assets:
            run([*gpg, asset])
            signatures.append(asset.with_name(asset.name + ".asc"))

        command = [
            "gh",
            "release",
            "create",
            args.version_tag,
            "--draft",
            "--generate-notes",
            "--verify-tag",
            "--repo",
            GITHUB_REPO,
            *assets,
            *signatures,
        ]
        if args.dry_run:
            print("Dry run, not running:", shlex.join(str(arg) for arg in command))
        else:
            run(command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
