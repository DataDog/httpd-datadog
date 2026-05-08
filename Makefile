# Pin the image name so it doesn't drift with the worktree directory name
# (the upstream default is derived from $(notdir $(CURDIR)) — fine for a
# canonical clone called `httpd-datadog`, wrong for any feature-branch
# worktree). Matches DEVCONTAINER_IMAGE_NAME in .gitlab-ci.yml.
DEV_CONTAINER_IMAGE_NAME := registry.ddbuild.io/ci/httpd-datadog/devcontainer

# The devcontainer Dockerfile pulls toolchain files from the
# nginx-datadog submodule's build_env/. Without this guard the staging
# step silently produces a tree missing those files and the resulting
# tag mismatches what CI computes — fail loudly instead.
#
# Skipped for `ci-build`, which runs its own `git submodule update`
# inline (the GitHub workflows checkout without submodules and init
# them as part of the build). All other targets (dev-image,
# test-integration, mirror-public-image) genuinely need build_env
# already present and keep the guard.
ifneq ($(MAKECMDGOALS),ci-build)
DEV_CONTAINER_REQUIRED_PATHS := deps/nginx-datadog/build_env/Toolchain.cmake.x86_64
endif

include .devcontainer/devcontainer.mk

# Fast-path for hot callers (test-integration, pre-commit hooks, …):
# skip the stage+hash+docker-pull cycle when .image-ref is already
# resolved. Run `make dev-image` explicitly to refresh after a
# Dockerfile or context.files change. Lives here (not in devcontainer.mk)
# because that file is upstream-synced.
.PHONY: dev-image-cached
ifeq ($(_DEV_CONTAINER_INSIDE),1)
dev-image-cached:
	@:
else
dev-image-cached:
	@[ -f $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref ] || $(MAKE) dev-image
endif

.PHONY: test-integration
test-integration: dev-image-cached
	$(IN_DEVCONTAINER) .devcontainer/run-integration-tests.sh

# One-shot CI build: trust the workdir, init the submodules cmake
# actually consumes, configure/build/install. Used by every job in
# .github/workflows/ that produces mod_datadog.so. Switch presets via
# PRESET=ci-release. inject-browser-sdk is omitted from the submodule
# list because RUM is off by default (HTTPD_DATADOG_ENABLE_RUM=OFF).
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
