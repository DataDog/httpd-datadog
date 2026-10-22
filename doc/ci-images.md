# Public CI image

GitLab builds the devcontainer in `registry.ddbuild.io/ci/httpd-datadog/devcontainer`.
The `devcontainer_to_public` job copies its plain amd64 OCI image through
`dd-pkg publish-image`, Artifact Gateway, and `public-images`.

The public destination is `httpd-datadog-ci-dev`. The `dev` registry set publishes
to Docker Hub and the Datadog public registries. The `-dev` suffix selects the
development authorization tier. This is a CI image, not a customer release.

Each default-branch push publishes the content-hash tag if it is missing. After
that publication succeeds, it advances `main`. GitHub Actions pulls
`registry.datadoghq.com/httpd-datadog-ci-dev:main` without registry credentials.

## Onboarding and first publication

Complete these steps before merging the registry cutover:

1. Request the `datadog/httpd-datadog-ci-dev` Docker Hub repository through
   [Freshservice](https://datadog.freshservice.com/support/catalog/items/357).
   Content-hash tags should be immutable; `main` must remain movable.
2. Ask [Agent Delivery](https://dd.enterprise.slack.com/archives/C06PQ7H6PHP) to
   authorize project `httpd-datadog`, source
   `registry.ddbuild.io/ci/httpd-datadog/devcontainer`, and destination
   `httpd-datadog-ci-dev` in Artifact Gateway. Confirm the owning Directory
   Service group and development-tier policy. GitLab already uses service
   account `httpd-datadog`.
3. Seed the public content-hash and `main` tags from the latest successful main
   build. Use `DEVCONTAINER_IMAGE_AMD64` and `CI_IMAGE_HASH` from that pipeline's
   `devcontainer_image` dotenv artifact. Do not use the `-ci` Nydus image.
4. Verify an anonymous pull before switching the workflows:

   ```sh
   docker pull registry.datadoghq.com/httpd-datadog-ci-dev:main
   ```

`registry.datadoghq.com` needs no separate repository provisioning. An ECR
Public repository is not needed for the `dev` registry set.

See [Publish public container images with dd-pkg](https://datadoghq.atlassian.net/wiki/spaces/BARX/pages/6948160674)
and the [PHP CI publisher](https://github.com/DataDog/dd-trace-php/blob/master/.gitlab/generate-ci-images.php).
The central gateway policy and dd-pkg update campaign are managed in `dd-source`.

## Publisher tests

Run the command-construction and failure-handling tests without publishing:

```sh
python3 -m unittest discover -s test/ci -p test_publish_devcontainer.py
```
