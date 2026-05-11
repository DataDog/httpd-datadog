# Pin the image name so it doesn't drift with the worktree directory name
# (the upstream default is derived from $(notdir $(CURDIR)) — fine for a
# canonical clone called `httpd-datadog`, wrong for any feature-branch
# worktree). Matches DEVCONTAINER_IMAGE_NAME in .gitlab-ci.yml.
DEV_CONTAINER_IMAGE_NAME := registry.ddbuild.io/ci/httpd-datadog/devcontainer

# The devcontainer Dockerfile pulls toolchain files from the
# nginx-datadog submodule's build_env/. Without this guard the staging
# step silently produces a tree missing those files and the resulting
# tag mismatches what CI computes — fail loudly instead. Upstream gates
# this check to devcontainer-touching targets only, so `ci-build` (which
# inits its own submodules in the recipe) and unrelated targets aren't
# blocked at parse time.
DEV_CONTAINER_REQUIRED_PATHS := deps/nginx-datadog/build_env/Toolchain.cmake.x86_64

include .devcontainer/devcontainer.mk

# Build mod_datadog (with RUM, against the cross-compile sysroot) inside
# the devcontainer and run the full pytest integration-test suite.
# MODULE_PATH=<path> skips the cmake build and points pytest at a pre-built
# artifact — the .gitlab-ci.yml test-integration:* jobs use this to reuse
# the build:* artifact instead of recompiling per test job.
#
# Pytest options use `--flag=VALUE`: pytest's early arg parser runs before
# conftest registers `--bin-path`/`--module-path`, so the space-separated
# form gets read as a positional test path and silently skips conftest.
#
# UV_PROJECT_ENVIRONMENT points outside the bind-mounted repo so a
# host-side `uv sync` (darwin/arm64 wheels) can't shadow the container's
# Linux venv.
MODULE_PATH ?=

.PHONY: test-integration
test-integration: dev-image
	$(IN_DEVCONTAINER) sh -ec '\
		arch=$$(uname -m); \
		git config --global --add safe.directory "$$PWD"; \
		module_path="$(MODULE_PATH)"; \
		if [ -z "$$module_path" ]; then \
			cmake --preset=ci-release \
				-DHTTPD_DATADOG_ENABLE_RUM=ON \
				-DCMAKE_TOOLCHAIN_FILE=/sysroot/$${arch}-none-linux-musl/Toolchain.cmake \
				-B build-container .; \
			cmake --build build-container -j; \
			rm -rf dist-container; \
			cmake --install build-container --prefix dist-container; \
			module_path="$$PWD/dist-container/lib/mod_datadog.so"; \
		fi; \
		repo_root=$$PWD; \
		cd test/integration-test; \
		export UV_PROJECT_ENVIRONMENT=/root/.venv-httpd-datadog-tests; \
		uv sync; \
		uv run pytest \
			--bin-path=/httpd/httpd-build/bin/apachectl \
			--module-path="$$module_path" \
			--log-dir="$$repo_root/logs" \
			-v'

# One-shot CI build: trust the workdir, init the submodules cmake
# actually consumes, configure/build/install. Used by every job in
# .github/workflows/ that produces mod_datadog.so. Switch presets via
# PRESET=ci-release. inject-browser-sdk is omitted from the submodule
# list because RUM is off by default (HTTPD_DATADOG_ENABLE_RUM=OFF).
PRESET ?= ci-dev
.PHONY: ci-build
ci-build:
	git config --global --add safe.directory "$(CURDIR)"
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
