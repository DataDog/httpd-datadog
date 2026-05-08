# CI image used by GitHub Actions

The workflows in this directory pin `image:` to
`datadog/docker-library:httpd-datadog-ci-<hash>` — a public Docker Hub
mirror of the internal devcontainer image built by GitLab CI from
[`.devcontainer/Dockerfile`](../../.devcontainer/Dockerfile). The build
+ caching pipeline lives in [`.gitlab/devcontainer.yml`](../../.gitlab/devcontainer.yml);
the image-tag hash is the sha256 of the staged build context defined
by [`.devcontainer/context.files`](../../.devcontainer/context.files).

GitHub-hosted runners can't pull from `registry.ddbuild.io`, so we
periodically copy the latest amd64 variant to Docker Hub and bump the
`image:` reference in each workflow.

## Bumping the image

Once GitLab CI has published a new tag (any change to a path listed in
`.devcontainer/context.files` invalidates the cache and triggers a
rebuild), mirror it from the repo root:

```sh
make mirror-public-image
```

The target stages the build context, computes the same 12-char hash
GitLab uses, pulls `registry.ddbuild.io/ci/httpd-datadog/devcontainer:amd64-<hash>`,
retags it as `datadog/docker-library:httpd-datadog-ci-<hash>`, and
pushes. It then prints the exact `image:` value to copy into:

- `dev.yml` (build + test jobs)
- `release.yml` (build job)
- `system-tests.yml` (build-artifacts job)

## Why two image namespaces

| Consumer        | Pull from                                                                  | Why |
|-----------------|----------------------------------------------------------------------------|-----|
| GitLab CI       | `registry.ddbuild.io/ci/httpd-datadog/devcontainer:<arch>-<hash>`          | private, fast, nydus-optimized |
| GitHub Actions  | `datadog/docker-library:httpd-datadog-ci-<hash>` (mirrored from the above) | public, reachable from GitHub-hosted runners |
| Local `make`    | Either of the above (pull `registry.ddbuild.io/...` if you have access; build locally otherwise) | dev convenience |

The two mirrors stay in sync only as far as the most recent
`make mirror-public-image` run — bump the workflows promptly after
running it.
