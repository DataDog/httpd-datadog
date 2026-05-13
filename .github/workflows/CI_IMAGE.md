# GitHub Actions CI image

GitHub-hosted runners can't pull from `registry.ddbuild.io`, so the
workflows here pin `image:` to a public Docker Hub mirror of the
GitLab-built devcontainer image.

Run this **from `main`** after a `.devcontainer/` change has landed
(the GitLab pipeline publishes the new tag; this just retags it to
Docker Hub and updates the workflow `image:` pins):

```sh
make mirror-public-image
```

The target pulls the latest amd64 build, retags it under
`datadog/docker-library:httpd-datadog-ci-<hash>`, pushes, and prints
the exact `image:` value to paste into `dev.yml`, `release.yml`, and
`system-tests.yml`.
