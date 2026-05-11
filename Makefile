# The CI image used for some GitHub jobs is built by the GitLab build-ci-image job.
# The hash is computed by this GitLab job from the files used to build the image.
#
# Whenever this image needs to be updated, one should:
#   - Get the hash from a run of the GitLab build-ci-image job.
#   - Copy this hash here, and in the GitHub workflow files.
#   - Run: make replicate-ci-image-for-github.

CI_DOCKER_IMAGE_HASH ?= bf4e353dec1442b7864fddc3c2618b8541eed4c04fe2ab88f2a4c2ebea61df91
CI_IMAGE_FROM_GITLAB ?= registry.ddbuild.io/ci/httpd-datadog/amd64:$(CI_DOCKER_IMAGE_HASH)
CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB ?= datadog/docker-library:httpd-datadog-ci-$(CI_DOCKER_IMAGE_HASH)

.PHONY: replicate-ci-image-for-github
replicate-ci-image-for-github:
	docker pull $(CI_IMAGE_FROM_GITLAB)
	docker tag $(CI_IMAGE_FROM_GITLAB) $(CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB)
	docker push $(CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB)
