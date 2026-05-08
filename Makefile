# Pin the image name so it doesn't drift with the worktree directory name
# (the upstream default is derived from $(notdir $(CURDIR)) — fine for a
# canonical clone called `httpd-datadog`, wrong for any feature-branch
# worktree). Matches DEVCONTAINER_IMAGE_NAME in .gitlab-ci.yml.
DEV_CONTAINER_IMAGE_NAME := registry.ddbuild.io/ci/httpd-datadog/devcontainer

# The devcontainer Dockerfile pulls toolchain files from the
# nginx-datadog submodule's build_env/. Without this guard the staging
# step silently produces a tree missing those files and the resulting
# tag mismatches what CI computes — fail loudly instead.
DEV_CONTAINER_REQUIRED_PATHS := deps/nginx-datadog/build_env/Toolchain.cmake.x86_64

include .devcontainer/devcontainer.mk

.PHONY: test-integration
test-integration: dev-image
	$(IN_DEVCONTAINER) .devcontainer/run-integration-tests.sh

# One-shot CI build: configure + build + install mod_datadog. Used by
# every job in .github/workflows/ that produces the shared library
# artifact (dev/release/system-tests). Assumes it runs inside the
# pinned devcontainer image (toolchain + httpd already present);
# callers pick the preset via PRESET=ci-dev|ci-release.
#
# `safe.directory` is a noop on hosts but required when actions/checkout
# clones into a path GitHub's runner UID doesn't own — the case for our
# container jobs. The submodule list deliberately omits inject-browser-sdk;
# the GitHub workflows here build without RUM (HTTPD_DATADOG_ENABLE_RUM=OFF
# by default in the cmake presets), so pulling it would be wasted bytes.
PRESET ?= ci-dev
.PHONY: ci-build
ci-build:
	git config --global --add safe.directory $(CURDIR)
	git submodule update --init --depth=1 deps/dd-trace-cpp deps/nginx-datadog
	cmake --preset=$(PRESET) -B build .
	cmake --build build -j --verbose
	cmake --install build --prefix dist

# GitHub-hosted runners can't pull from registry.ddbuild.io; the workflows
# in .github/workflows/ pin to a public Docker Hub mirror at
# datadog/docker-library:httpd-datadog-ci-<hash>. After a new tag is built
# by .gitlab/devcontainer.yml (any change to .devcontainer/context.files
# inputs invalidates the cache), run this target to copy the amd64 variant
# to Docker Hub and bump the workflows.
# See .github/workflows/CI_IMAGE.md for the bump procedure.
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
