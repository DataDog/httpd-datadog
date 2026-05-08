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
