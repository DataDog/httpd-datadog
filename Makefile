# Keep the image name stable across differently named worktrees.
# This matches DEVCONTAINER_IMAGE_NAME in .gitlab-ci.yml.
DEV_CONTAINER_IMAGE_NAME := registry.ddbuild.io/ci/httpd-datadog/devcontainer
DEV_CONTAINER_PER_ARCH := true

# Fail devcontainer targets early when their toolchain input is absent.
# The shared makefile applies this guard only to relevant targets.
DEV_CONTAINER_REQUIRED_PATHS := deps/nginx-datadog/build_env/Toolchain.cmake.x86_64

CI_DOCKER_IMAGE_HASH ?= bf4e353dec1442b7864fddc3c2618b8541eed4c04fe2ab88f2a4c2ebea61df91
CI_IMAGE_FROM_GITLAB ?= registry.ddbuild.io/ci/httpd-datadog/amd64:$(CI_DOCKER_IMAGE_HASH)
CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB ?= datadog/docker-library:httpd-datadog-ci-$(CI_DOCKER_IMAGE_HASH)

include .devcontainer/devcontainer.mk

# CI supplies MODULE_PATH to reuse its architecture-specific build.
MODULE_PATH ?=

.PHONY: test-integration
test-integration: dev-image
	$(IN_DEVCONTAINER) env MODULE_PATH="$(MODULE_PATH)" .devcontainer/run-integration-tests.sh

# GitHub build entrypoint. RUM is off, so inject-browser-sdk is unnecessary.
PRESET ?= ci-dev
.PHONY: ci-build
ci-build:
	git config --global --add safe.directory "$(CURDIR)"
	git submodule update --init --depth=1 deps/dd-trace-cpp deps/nginx-datadog
	cmake --preset=$(PRESET) -B build .
	cmake --build build -j --verbose
	cmake --install build --prefix dist

# Mirror the plain amd64 OCI image for GitHub-hosted runners.
# See .github/workflows/CI_IMAGE.md for the release procedure.
.PHONY: mirror-public-image
mirror-public-image:
	@$(MAKE) -s -f .devcontainer/devcontainer.mk .devcontainer-stage-context
	@hash=$$($(MAKE) -s -f .devcontainer/devcontainer.mk .devcontainer-image-hash); \
	src="$(DEV_CONTAINER_IMAGE_NAME):amd64-$$hash"; \
	public="datadog/docker-library:httpd-datadog-ci-$$hash"; \
	echo "Mirroring $$src -> $$public"; \
	docker pull --platform linux/amd64 "$$src"; \
	docker tag "$$src" "$$public"; \
	docker push "$$public"; \
	echo ""; \
	echo "Update image: in .github/workflows/{dev,release,system-tests}.yml to:"; \
	echo "  $$public"
