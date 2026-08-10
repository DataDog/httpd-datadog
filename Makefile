# Keep the image name stable across differently named worktrees.
# This matches DEVCONTAINER_IMAGE_NAME in .gitlab-ci.yml.
DEV_CONTAINER_IMAGE_NAME := registry.ddbuild.io/ci/httpd-datadog/devcontainer
DEV_CONTAINER_PER_ARCH := true

# Fail devcontainer targets early when their toolchain input is absent.
# The shared makefile applies this guard only to relevant targets.
DEV_CONTAINER_REQUIRED_PATHS := deps/nginx-datadog/build_env/Toolchain.cmake.x86_64

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
