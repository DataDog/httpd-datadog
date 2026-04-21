DEV_CONTAINER_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
DEV_CONTAINER_REPO_ROOT := $(abspath $(DEV_CONTAINER_DIR)/..)

# When running inside the container, tools are available directly.
# Check for /.dockerenv (Docker) or KUBERNETES_SERVICE_HOST (Kubernetes CI).
ifneq ($(or $(wildcard /.dockerenv),$(KUBERNETES_SERVICE_HOST)),)

DEVCONTAINER_RUN :=

.PHONY: dev-image
dev-image:
	@true

else

# Fail fast with actionable guidance if deps/nginx-datadog isn't populated —
# without this check, the DEV_CONTAINER_HASH `find` below emits warnings and
# silently hashes an incomplete input set, producing a tag that doesn't
# match what CI computed and triggering confusing pull-then-fall-back-to-
# build behavior.
ifeq ($(wildcard $(DEV_CONTAINER_REPO_ROOT)/deps/nginx-datadog/build_env/Toolchain.cmake.x86_64),)
$(error deps/nginx-datadog submodule is not initialized. Run: git submodule update --init --recursive)
endif

DEV_CONTAINER_REGISTRY ?= registry.ddbuild.io
DEV_CONTAINER_IMAGE_NAME ?= $(DEV_CONTAINER_REGISTRY)/ci/httpd-datadog

# Match the hash computation in .gitlab/devcontainer.yml (devcontainer-image
# job): sha256 over .devcontainer/Dockerfile, deps/nginx-datadog/build_env/,
# and scripts/setup-httpd.py.
DEV_CONTAINER_HASH := $(shell cd $(DEV_CONTAINER_REPO_ROOT) && \
  find .devcontainer/Dockerfile deps/nginx-datadog/build_env/ scripts/setup-httpd.py -type f | sort | \
  while IFS= read -r f; do echo "--- $$f ---"; cat "$$f"; done | \
  (command -v sha256sum >/dev/null 2>&1 && sha256sum || shasum -a 256) | cut -d' ' -f1)

DEV_CONTAINER_TAG := $(DEV_CONTAINER_HASH)
DEV_CONTAINER_IMAGE := $(DEV_CONTAINER_IMAGE_NAME):$(DEV_CONTAINER_TAG)

# Map host arch (uname -m) to the Dockerfile's ARCH build-arg.
DEV_CONTAINER_HOST_ARCH := $(shell uname -m)
ifeq ($(DEV_CONTAINER_HOST_ARCH),arm64)
DEV_CONTAINER_ARCH := aarch64
DEV_CONTAINER_PLATFORM := linux/arm64
else ifeq ($(DEV_CONTAINER_HOST_ARCH),aarch64)
DEV_CONTAINER_ARCH := aarch64
DEV_CONTAINER_PLATFORM := linux/arm64
else
DEV_CONTAINER_ARCH := x86_64
DEV_CONTAINER_PLATFORM := linux/amd64
endif

# For git worktrees, .git is a file pointing to a gitdir outside the repo root;
# bind-mount the git common-dir so `git` works inside the container.
DEV_CONTAINER_GIT_COMMON_DIR := $(shell cd $(DEV_CONTAINER_REPO_ROOT) && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
ifneq ($(DEV_CONTAINER_GIT_COMMON_DIR),)
ifneq ($(DEV_CONTAINER_GIT_COMMON_DIR),$(DEV_CONTAINER_REPO_ROOT)/.git)
DEV_CONTAINER_GIT_MOUNT := -v $(DEV_CONTAINER_GIT_COMMON_DIR):$(DEV_CONTAINER_GIT_COMMON_DIR)
endif
endif

DEVCONTAINER_RUN = docker run --rm \
	-v $(DEV_CONTAINER_REPO_ROOT):$(DEV_CONTAINER_REPO_ROOT) \
	$(DEV_CONTAINER_GIT_MOUNT) \
	-w $(DEV_CONTAINER_REPO_ROOT) \
	$(DEV_CONTAINER_IMAGE)

# Ensure the dev container image is available locally. Prefer pulling from the
# registry (CI builds every tagged hash); fall back to a local build.
# Stale images with different tags are removed first.
.PHONY: dev-image
dev-image:
	@if ! docker image inspect $(DEV_CONTAINER_IMAGE) >/dev/null 2>&1; then \
		stale=$$(docker images --format '{{.Repository}}:{{.Tag}}' $(DEV_CONTAINER_IMAGE_NAME) 2>/dev/null | grep -v ':$(DEV_CONTAINER_TAG)$$' || true); \
		if [ -n "$$stale" ]; then \
			echo "Removing stale dev container image(s): $$stale"; \
			docker rmi $$stale || true; \
		fi; \
		if docker pull $(DEV_CONTAINER_IMAGE) >/dev/null 2>&1; then \
			echo "Pulled $(DEV_CONTAINER_IMAGE)"; \
		else \
			echo "Building dev container image $(DEV_CONTAINER_IMAGE)..."; \
			docker buildx build \
				--platform $(DEV_CONTAINER_PLATFORM) \
				--build-arg ARCH=$(DEV_CONTAINER_ARCH) \
				--load \
				-t $(DEV_CONTAINER_IMAGE) \
				-f $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/Dockerfile \
				$(DEV_CONTAINER_REPO_ROOT); \
		fi; \
	fi

.PHONY: dev-shell
dev-shell: dev-image
	docker run --rm -it \
		-v $(DEV_CONTAINER_REPO_ROOT):$(DEV_CONTAINER_REPO_ROOT) \
		$(DEV_CONTAINER_GIT_MOUNT) \
		-w $(DEV_CONTAINER_REPO_ROOT) \
		$(DEV_CONTAINER_IMAGE) \
		/bin/sh

.PHONY: dev-image-clean
dev-image-clean:
	@stale=$$(docker images --format '{{.Repository}}:{{.Tag}}' $(DEV_CONTAINER_IMAGE_NAME) 2>/dev/null | grep -v ':$(DEV_CONTAINER_TAG)$$' || true); \
	if [ -n "$$stale" ]; then \
		echo "Removing stale dev container image(s): $$stale"; \
		docker rmi $$stale; \
	else \
		echo "No stale dev container images found."; \
	fi

endif

# Always-available targets: $(DEVCONTAINER_RUN) is empty inside the container
# (the script runs directly) and `docker run …` outside, so one definition
# works in both modes.
.PHONY: test-integration
test-integration: dev-image
	$(DEVCONTAINER_RUN) .devcontainer/run-integration-tests.sh
