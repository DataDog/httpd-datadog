#!/usr/bin/env python3
"""Create a draft GitHub release from the GitLab pipeline of a version tag.

Usage:
    scripts/release.py --version-tag v1.2.3 [--pipeline-id ID] [--local-user KEYID]
    scripts/release.py --version-tag v1.2.3 --pipeline-id ID --dry-run --out-dir DIR

The script downloads the module builds of the pipeline, zips them, signs each
zip with GPG and creates a draft release with `gh`. Publishing the release
stays manual.

GitLab token: GITLAB_TOKEN, or `ddtool auth gitlab token`.
"""

import argparse
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
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
    return result.stdout.strip().splitlines()[-1]


def gitlab_get(path: str, token: str) -> bytes:
    url = f"{GITLAB_API}/projects/{GITLAB_PROJECT}{path}"
    print("+ GET", url, file=sys.stderr)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        raise SystemExit(f"GitLab API error {error.code} for {url}: {body}") from error


def find_pipeline(tag: str, token: str) -> int:
    pipelines = json.loads(gitlab_get(f"/pipelines?ref={quote(tag, safe='')}&per_page=1", token))
    if not pipelines:
        raise SystemExit(f"No pipeline found for tag {tag}.")
    return pipelines[0]["id"]


def pipeline_jobs(pipeline_id: int, token: str) -> dict[str, dict]:
    jobs = {}
    page = 1
    while page_jobs := json.loads(
        gitlab_get(f"/pipelines/{pipeline_id}/jobs?per_page=100&page={page}", token)
    ):
        for job in page_jobs:
            # Keep the latest attempt of retried jobs.
            if job["name"] not in jobs or job["id"] > jobs[job["name"]]["id"]:
                jobs[job["name"]] = job
        page += 1

    failed = [
        name
        for name, job in jobs.items()
        if job["status"] not in ("success", "manual", "skipped", "created")
        and not job["allow_failure"]
    ]
    if failed:
        raise SystemExit(f"Pipeline {pipeline_id} has unsuccessful jobs: {', '.join(failed)}")
    return jobs


def write_zip(path: Path, name: str, data: bytes) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr(name, data)


def prepare_assets(jobs: dict[str, dict], token: str, out_dir: Path) -> list[Path]:
    assets = []
    for prefix, (job_name, arch) in ASSETS.items():
        job = jobs.get(job_name)
        if job is None or job["status"] != "success":
            raise SystemExit(f"Job {job_name} is missing or did not succeed.")
        artifacts = zipfile.ZipFile(io.BytesIO(gitlab_get(f"/jobs/{job['id']}/artifacts", token)))
        for suffix, name in (("", "mod_datadog.so"), ("-debug", "mod_datadog.so.debug")):
            member = f"artifacts/{arch}/{name}"
            if member not in artifacts.namelist():
                raise SystemExit(f"Job {job_name} artifacts have no {member}.")
            asset = out_dir / f"{prefix}{suffix}.zip"
            write_zip(asset, name, artifacts.read(member))
            assets.append(asset)
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version-tag", required=True, help="Version tag, for example v1.2.3.")
    parser.add_argument("--pipeline-id", type=int, help="GitLab pipeline ID. Default: latest pipeline of the tag.")
    parser.add_argument("--local-user", help="GPG key used to sign the assets. Default: gpg default key.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare and sign the assets, but do not create the release.")
    parser.add_argument("--out-dir", type=Path, help="Keep the assets in this directory.")
    args = parser.parse_args()

    token = gitlab_token()
    pipeline_id = args.pipeline_id or find_pipeline(args.version_tag, token)
    print(f"Pipeline: https://gitlab.ddbuild.io/DataDog/httpd-datadog/-/pipelines/{pipeline_id}")
    jobs = pipeline_jobs(pipeline_id, token)

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
            "gh", "release", "create", args.version_tag,
            "--draft", "--generate-notes", "--verify-tag",
            "--repo", GITHUB_REPO,
            *assets, *signatures,
        ]
        if args.dry_run:
            print("Dry run, not running:", shlex.join(str(arg) for arg in command))
        else:
            run(command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
