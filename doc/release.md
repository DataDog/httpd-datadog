# Release

## Versioning

This module adheres to the principles of [Semantic Versioning (SemVer)](https://semver.org/). The
version number is expressed as MAJOR.MINOR.PATCH, with the following guidelines:

- MAJOR version: Increment for incompatible API changes.
- MINOR version: Increment for backward-compatible feature additions.
- PATCH version: Increment for backward-compatible bug fixes.

## Compatibility Requirements

Since this module is extending Apache HTTP Server capabilities using the C interface, each versions
are tied to a specific version of the webserver. Each module version will receive support for the
specified HTTPD version range until the respective HTTPD versions reach their end-of-life.

The following table outlines the compatibility between module versions and HTTPD versions:

| `mod_datadog` version | HTTPD Version Range | Status  |
| --------------------- | ------------------- | ------- |
| 1.0.0                 | 2.4.0 - 2.4.54      | Current |

## Artifacts

Release artifact are generated through a Continuous Integration pipeline. Our CI infrastructure
ensures cross-platform compatibility by compiling shared libraries for both Linux `x86_64` and
`arm64` architectures. It generates shared libaries for each HTTPD version supported.

### GitHub Release and S3

All release files come from the GitLab pipeline of the version tag.

1. Push the `vX.Y.Z` tag. The `upload-release` job uploads the RUM builds to
   `s3://rum-auto-instrumentation/httpd/<YYYY_MM_DD>_vX.Y.Z_<sha>/`.
2. When the pipeline is green, create the draft GitHub release:

   ```sh
   scripts/release.py --version-tag vX.Y.Z
   ```

   It downloads the builds, signs each zip with your GPG key (`--local-user` to pick one) and
   creates the draft with `gh`. Use `--dry-run --out-dir DIR` to only prepare the files.

   | Asset | Build |
   | ----- | ----- |
   | `mod_datadog_artifact.zip`, `mod_datadog_artifact-debug.zip` | `x86_64`, RUM disabled at build time |
   | `mod_datadog-amd64.zip`, `mod_datadog-amd64-debug.zip` | `x86_64`, RUM |
   | `mod_datadog-arm64.zip`, `mod_datadog-arm64-debug.zip` | `arm64`, RUM |

3. Run the smoke tests.
4. Publish the release:

   ```sh
   scripts/release.py --version-tag vX.Y.Z --publish
   ```

   It runs the manual `promote-s3-latest` job, which copies the S3 files to `httpd/latest/`, then
   publishes the draft.

### OCI Package

The same modules are also published as an OCI package named `datadog-apm-library-httpd`, through
the shared *one-pipeline* GitLab template (`.gitlab/one-pipeline.locked.yml`). This is the artifact
the fleet installer delivers to `/opt/datadog-packages/datadog-apm-library-httpd/`.

Its version comes from `.gitlab/package-version.sh`, not from `project(... VERSION)` in
`CMakeLists.txt`. A `vX.Y.Z` tag publishes `X.Y.Z`. Other pipelines publish
`<last release>-dev.b<branch hash>.glci<pipeline>.g<sha>`.

Pushing a tag that matches `^v?[0-9]+\.[0-9]+\.[0-9]+$` makes `promote-oci-to-prod` fire
automatically. It also publishes the `dd-lib-httpd-init` image. Other tags run like a branch
pipeline and do not publish to prod.
