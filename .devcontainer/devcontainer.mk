# DO NOT EDIT. Synced from DataDog/libdatadog-build by the
# libdatadog-build devcontainer-bundle campaigner — edits here will be
# overwritten on the next run.
# Source of truth: https://github.com/DataDog/libdatadog-build/blob/main/repository-tools/sync/devcontainer.mk
#
# Inputs (set before `include`):
#   DEV_CONTAINER_REPO_ROOT          Absolute path to the repo root.
#   DEV_CONTAINER_IMAGE_NAME         Override image name. Defaults to
#                                    registry.ddbuild.io/ci/<repo>/devcontainer.
#   DEV_CONTAINER_REQUIRED_PATHS     Whitespace-separated paths that must exist
#                                    (e.g. submodule checkouts). Missing ->
#                                    $(error).
#   DOCKER_BUILDX_FLAGS              Extra flags appended to the local build.

DEV_CONTAINER_REPO_ROOT ?= $(CURDIR)
_DEV_CONTAINER_REPO_NAME := $(notdir $(patsubst %/,%,$(DEV_CONTAINER_REPO_ROOT)))
DEV_CONTAINER_IMAGE_NAME ?= registry.ddbuild.io/ci/$(_DEV_CONTAINER_REPO_NAME)/devcontainer

_DEV_CONTAINER_CONTEXT_FILES := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/context.files
_DEV_CONTAINER_CONTEXT_FILTER := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/context.filter
_DEV_CONTAINER_DOCKERFILE := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/Dockerfile

# uname -m -> docker --platform / conventional ARCH build-arg.
_DEV_CONTAINER_UNAME_M := $(shell uname -m)
ifeq ($(_DEV_CONTAINER_UNAME_M),arm64)
  _DEV_CONTAINER_PLATFORM := linux/arm64
  _DEV_CONTAINER_ARCH := aarch64
else ifeq ($(_DEV_CONTAINER_UNAME_M),aarch64)
  _DEV_CONTAINER_PLATFORM := linux/arm64
  _DEV_CONTAINER_ARCH := aarch64
else
  _DEV_CONTAINER_PLATFORM := linux/amd64
  _DEV_CONTAINER_ARCH := x86_64
endif

# Pass --build-arg ARCH only if the Dockerfile actually declares it.
_DEV_CONTAINER_ARCH_ARG := $(shell grep -q '^ARG ARCH' $(_DEV_CONTAINER_DOCKERFILE) 2>/dev/null && echo --build-arg ARCH=$(_DEV_CONTAINER_ARCH))

# Skip everything inside the container (no nested docker, no pull).
_DEV_CONTAINER_INSIDE := $(shell [ -f /.dockerenv ] || [ -n "$$KUBERNETES_SERVICE_HOST" ] && echo 1)

# Stage .devcontainer/context.files (+ optional context.filter) into a tmp dir,
# verify Dockerfile is present, echo the tmpdir. Single source of truth for
# both the tag hash and the buildx context.
define _dev_container_stage_context
ctx=$$(mktemp -d); \
trap 'rm -rf "$$ctx"' EXIT; \
if [ ! -f "$(_DEV_CONTAINER_CONTEXT_FILES)" ]; then \
  echo "ERROR: $(_DEV_CONTAINER_CONTEXT_FILES) not found" >&2; exit 1; \
fi; \
filter_flag=""; \
if [ -f "$(_DEV_CONTAINER_CONTEXT_FILTER)" ]; then \
  filter_flag="--filter=merge $(_DEV_CONTAINER_CONTEXT_FILTER)"; \
fi; \
grep -Ev '^\s*(#|$$)' "$(_DEV_CONTAINER_CONTEXT_FILES)" | \
  rsync -aR --files-from=- $$filter_flag "$(DEV_CONTAINER_REPO_ROOT)/" "$$ctx/"; \
if [ ! -f "$$ctx/.devcontainer/Dockerfile" ]; then \
  echo "ERROR: .devcontainer/Dockerfile not staged; check .devcontainer/context.files" >&2; \
  exit 1; \
fi
endef

# Compute the 12-char tag hash from the staged tree.
define _dev_container_compute_tag
tag=$$(cd "$$ctx" && find . -type f | sort | \
  while IFS= read -r f; do printf -- '--- %s ---\n' "$$f"; cat "$$f"; done | \
  sha256sum | cut -c1-12)
endef

# Git-worktree support: when .git is a gitdir pointer, make the common dir
# visible inside the container so `git` calls work.
_DEV_CONTAINER_GIT_COMMON_DIR := $(shell cd $(DEV_CONTAINER_REPO_ROOT) && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
_DEV_CONTAINER_DEFAULT_GIT_DIR := $(DEV_CONTAINER_REPO_ROOT)/.git
ifneq ($(_DEV_CONTAINER_GIT_COMMON_DIR),)
  ifneq ($(_DEV_CONTAINER_GIT_COMMON_DIR),$(_DEV_CONTAINER_DEFAULT_GIT_DIR))
    _DEV_CONTAINER_WORKTREE_MOUNT := -v $(_DEV_CONTAINER_GIT_COMMON_DIR):$(_DEV_CONTAINER_GIT_COMMON_DIR)
  endif
endif

# Precondition check for caller-declared required paths.
ifneq ($(strip $(DEV_CONTAINER_REQUIRED_PATHS)),)
  _DEV_CONTAINER_MISSING_PATHS := $(foreach p,$(DEV_CONTAINER_REQUIRED_PATHS),$(if $(wildcard $(DEV_CONTAINER_REPO_ROOT)/$(p)),,$(p)))
  ifneq ($(strip $(_DEV_CONTAINER_MISSING_PATHS)),)
    $(error Missing required paths (did you init submodules?): $(_DEV_CONTAINER_MISSING_PATHS))
  endif
endif

.PHONY: dev-image dev-shell dev-tag dev-push .devcontainer-stage-context

# Stage the build context per .devcontainer/context.files into a stable
# path under .devcontainer/.staged/. Invoked from VS Code's
# initializeCommand (see .devcontainer/devcontainer.json) so that
# build.context = `.staged` gets the same narrow tree CI and
# `make dev-image` use — same files, same hash, shared cache.
# The hash-computing targets (dev-tag / dev-image / dev-push) keep
# using a mktemp dir for parallel safety; this target deliberately
# writes to a stable path because VS Code needs one.
# Name is dot-prefixed so it does not collide with consumer repos that
# may have their own `stage-context` target.
_DEV_CONTAINER_STAGED := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.staged

.devcontainer-stage-context:
	@rm -rf "$(_DEV_CONTAINER_STAGED)"
	@mkdir -p "$(_DEV_CONTAINER_STAGED)"
	@if [ ! -f "$(_DEV_CONTAINER_CONTEXT_FILES)" ]; then \
	  echo "ERROR: $(_DEV_CONTAINER_CONTEXT_FILES) not found" >&2; exit 1; \
	fi
	@filter_flag=""; \
	if [ -f "$(_DEV_CONTAINER_CONTEXT_FILTER)" ]; then \
	  filter_flag="--filter=merge $(_DEV_CONTAINER_CONTEXT_FILTER)"; \
	fi; \
	grep -Ev '^\s*(#|$$)' "$(_DEV_CONTAINER_CONTEXT_FILES)" | \
	  rsync -aR --files-from=- $$filter_flag "$(DEV_CONTAINER_REPO_ROOT)/" "$(_DEV_CONTAINER_STAGED)/"
	@test -f "$(_DEV_CONTAINER_STAGED)/.devcontainer/Dockerfile" || \
	  { echo "ERROR: .devcontainer/Dockerfile not staged; check .devcontainer/context.files" >&2; exit 1; }

# Print the tag that would be used. Useful for debugging.
dev-tag:
	@$(_dev_container_stage_context); \
	$(_dev_container_compute_tag); \
	echo "$(DEV_CONTAINER_IMAGE_NAME):$$tag"

# Pull the image if available; otherwise build locally from the staged context.
ifeq ($(_DEV_CONTAINER_INSIDE),1)
dev-image:
	@:
else
dev-image:
	@$(_dev_container_stage_context); \
	$(_dev_container_compute_tag); \
	ref="$(DEV_CONTAINER_IMAGE_NAME):$$tag"; \
	if docker pull "$$ref" >/dev/null 2>&1; then \
	  echo "Pulled $$ref"; \
	else \
	  echo "Pull miss; building $$ref locally"; \
	  docker buildx build \
	    --platform $(_DEV_CONTAINER_PLATFORM) \
	    --file "$$ctx/.devcontainer/Dockerfile" \
	    --build-context repo="$$ctx" \
	    $(_DEV_CONTAINER_ARCH_ARG) \
	    $(DOCKER_BUILDX_FLAGS) \
	    --load -t "$$ref" \
	    "$$ctx"; \
	fi; \
	echo "$$ref" > $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref
endif

# Manual push helper; used by repos that want to pre-warm the cache.
dev-push:
	@$(_dev_container_stage_context); \
	$(_dev_container_compute_tag); \
	ref="$(DEV_CONTAINER_IMAGE_NAME):$$tag"; \
	docker buildx build \
	  --platform $(_DEV_CONTAINER_PLATFORM) \
	  --file "$$ctx/.devcontainer/Dockerfile" \
	  --build-context repo="$$ctx" \
	  $(_DEV_CONTAINER_ARCH_ARG) \
	  $(DOCKER_BUILDX_FLAGS) \
	  --push -t "$$ref" \
	  "$$ctx"

# Interactive shell in the built image. Shares the repo root and, when a
# worktree is in use, the git common dir too.
DEVCONTAINER_RUN ?= docker run --rm -it \
  -v $(DEV_CONTAINER_REPO_ROOT):$(DEV_CONTAINER_REPO_ROOT) \
  $(_DEV_CONTAINER_WORKTREE_MOUNT) \
  -w $(DEV_CONTAINER_REPO_ROOT)

ifeq ($(_DEV_CONTAINER_INSIDE),1)
  DEVCONTAINER_RUN :=
endif

dev-shell: dev-image
	@ref=$$(cat $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref); \
	$(DEVCONTAINER_RUN) "$$ref" /bin/sh
