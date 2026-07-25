## Versioning
This module adheres to the principles of [Semantic Versioning (SemVer)](https://semver.org/). The version number is expressed as MAJOR.MINOR.PATCH, with the following guidelines:

- MAJOR version: Increment for incompatible API changes.
- MINOR version: Increment for backward-compatible feature additions.
- PATCH version: Increment for backward-compatible bug fixes.

We release at least one version per quarter. Nonetheless, we allow ourselves to release more if necessary.

## Compatibility Requirements

Since this module is extending [Apache HTTP Server]() capabilities using the C interface, each versions are tied to a specific version of the webserver.
Each module version will receive support for the specified HTTPD version range until the respective HTTPD versions reach their end-of-life.

The following table outlines the compatibility between module versions and HTTPD versions:

| `mod_datadog` version | HTTPD Version Range | Status  |
| --------------------- | ------------------- | ------- |
| 1.0.0                 | 2.4.0 - 2.4.54      | Current |

## Artifacts
Release artifact are generated through a Continuous Integration pipeline. Our CI infrastructure ensures cross-platform compatibility by compiling shared libraries for both Linux `x86_64` and `arm64` architectures. 
It generates shared libaries for each HTTPD version supported.

### OCI package

The same modules are also published as an OCI package named
`datadog-apm-library-httpd`, through the shared *one-pipeline* GitLab template
(`.gitlab/one-pipeline.locked.yml`). This is the artifact the fleet installer
delivers to `/opt/datadog-packages/datadog-apm-library-httpd/`.

Its version comes from the **git tag** (`$CI_COMMIT_TAG` with a leading `v`
stripped), not from `project(... VERSION)` in `CMakeLists.txt`. Untagged
pipelines publish as `0.0.1-<short-sha>`.

Pushing a tag that matches `^v?[0-9]+\.[0-9]+\.[0-9]+$` makes
`promote-oci-to-prod` fire automatically. Use a suffixed tag (for example
`v1.1.0-rc1`) or a plain branch pipeline for pre-releases.
