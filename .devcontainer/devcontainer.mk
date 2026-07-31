# DO NOT EDIT. Synced from DataDog/dd-repo-tools by the
# dd-repo-tools devcontainer-bundle campaigner — edits here will be
# overwritten on the next run.
# Source of truth: https://github.com/DataDog/dd-repo-tools/blob/main/shared/devcontainer/devcontainer.mk
#
# Inputs (set before `include`):
#   DEV_CONTAINER_REPO_ROOT          Absolute path to the repo root.
#   DEV_CONTAINER_IMAGE_NAME         Override image name. Defaults to
#                                    registry.ddbuild.io/ci/<repo>/devcontainer.
#   DEV_CONTAINER_REQUIRED_PATHS     Whitespace-separated paths that must exist
#                                    (e.g. submodule checkouts). Checked at
#                                    recipe time as a prereq of devcontainer-
#                                    touching targets — missing paths fail
#                                    that invocation, not parse time.
#   DEV_CONTAINER_PER_ARCH           Set to true when CI publishes
#                                    amd64-<hash> / arm64-<hash> tags.
#   DEV_CONTAINER_SHA256             Hash command. Auto-detects sha256sum or
#                                    the macOS-compatible shasum fallback.
#   DOCKER_BUILDX_FLAGS              Extra flags appended to the local build.
#
# This file is the single source of truth for staging + hashing. The
# GitLab template (devcontainer.yml) calls into `make` so both paths
# share the same code.

# Recipes need bash + pipefail: the hash pipeline (find | sort | SHA-256 |
# cut) silently produces an empty tag on any pipe failure under POSIX sh,
# which downstream becomes a malformed `image:` ref. Override after the
# include if you need a different shell for your own recipes.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

DEV_CONTAINER_REPO_ROOT ?= $(CURDIR)
_DEV_CONTAINER_REPO_NAME := $(notdir $(patsubst %/,%,$(DEV_CONTAINER_REPO_ROOT)))
DEV_CONTAINER_IMAGE_NAME ?= registry.ddbuild.io/ci/$(_DEV_CONTAINER_REPO_NAME)/devcontainer
DEV_CONTAINER_PER_ARCH ?=
DEV_CONTAINER_SHA256 ?= $(shell command -v sha256sum >/dev/null 2>&1 && echo sha256sum || { command -v shasum >/dev/null 2>&1 && echo 'shasum -a 256'; })

_DEV_CONTAINER_CONTEXT_FILES := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/context.files
_DEV_CONTAINER_CONTEXT_FILTER := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/context.filter
_DEV_CONTAINER_DOCKERFILE := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/Dockerfile
_DEV_CONTAINER_STAGED := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.staged
_DEV_CONTAINER_GIT_COMMON_LINK := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.git-common

# uname -m -> docker --platform / conventional ARCH build-arg.
_DEV_CONTAINER_UNAME_M := $(shell uname -m)
ifneq ($(filter $(_DEV_CONTAINER_UNAME_M),arm64 aarch64),)
  _DEV_CONTAINER_PLATFORM := linux/arm64
  _DEV_CONTAINER_DOCKER_ARCH := arm64
  _DEV_CONTAINER_ARCH := aarch64
else
  _DEV_CONTAINER_PLATFORM := linux/amd64
  _DEV_CONTAINER_DOCKER_ARCH := amd64
  _DEV_CONTAINER_ARCH := x86_64
endif

ifeq ($(DEV_CONTAINER_PER_ARCH),true)
  _DEV_CONTAINER_NATIVE_TAG_PREFIX := $(_DEV_CONTAINER_DOCKER_ARCH)-
  _DEV_CONTAINER_AMD64_TAG_PREFIX := amd64-
endif

# Pass --build-arg ARCH only if the Dockerfile actually declares it.
_DEV_CONTAINER_ARCH_ARG := $(shell grep -q '^ARG ARCH' $(_DEV_CONTAINER_DOCKERFILE) 2>/dev/null && echo --build-arg ARCH=$(_DEV_CONTAINER_ARCH))

# Skip everything inside the container (no nested docker, no pull).
_DEV_CONTAINER_INSIDE := $(shell [ -f /.dockerenv ] || [ -n "$$KUBERNETES_SERVICE_HOST" ] && echo 1)

# Stage .devcontainer/context.files (+ optional context.filter) into $$ctx.
# Caller sets $$ctx (and arranges cleanup if needed). Verifies Dockerfile
# was staged.
define _dev_container_stage_into_ctx
if [ ! -f "$(_DEV_CONTAINER_CONTEXT_FILES)" ]; then \
  echo "ERROR: $(_DEV_CONTAINER_CONTEXT_FILES) not found" >&2; exit 1; \
fi; \
files="$$ctx/.devcontainer-context-files"; \
grep -Ev '^[[:space:]]*(#|$$)' "$(_DEV_CONTAINER_CONTEXT_FILES)" > "$$files" || true; \
missing=; \
while IFS= read -r path; do \
  if [ ! -e "$(DEV_CONTAINER_REPO_ROOT)/$$path" ]; then \
    missing="$${missing}$${missing:+, }$$path"; \
  fi; \
done < "$$files"; \
if [ -n "$$missing" ]; then \
  echo "ERROR: context.files entries not found: $$missing" >&2; \
  rm -f "$$files"; \
  exit 1; \
fi; \
filter_arg=; \
[ -f "$(_DEV_CONTAINER_CONTEXT_FILTER)" ] && filter_arg="--filter=merge $(_DEV_CONTAINER_CONTEXT_FILTER)"; \
rsync -aR --files-from="$$files" $$filter_arg "$(DEV_CONTAINER_REPO_ROOT)/" "$$ctx/"; \
rm -f "$$files"; \
if [ ! -f "$$ctx/.devcontainer/Dockerfile" ]; then \
  echo "ERROR: .devcontainer/Dockerfile not staged; check .devcontainer/context.files" >&2; \
  exit 1; \
fi
endef

# Stage into a fresh mktemp dir, cleaned up on shell exit. Sets $$ctx.
define _dev_container_stage_context
ctx=$$(mktemp -d); \
trap 'rm -rf "$$ctx"' EXIT; \
$(_dev_container_stage_into_ctx)
endef

# Compute the 12-char tag hash from the staged tree at $$ctx.
define _dev_container_compute_tag
[ -n "$(DEV_CONTAINER_SHA256)" ] || { echo "ERROR: sha256sum or shasum is required" >&2; exit 1; }; \
tag=$$(cd "$$ctx" && find . -type f | LC_ALL=C sort | \
  while IFS= read -r f; do printf -- '--- %s ---\n' "$$f"; cat "$$f"; done | \
  $(DEV_CONTAINER_SHA256) | cut -c1-12); \
[ -n "$$tag" ] || { echo "ERROR: hash pipeline produced empty tag (empty staged context?)" >&2; exit 1; }
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

# Precondition check for caller-declared required paths. Wired as a
# phony prereq below so it fires only when a devcontainer-touching
# target is actually built — not at parse time, which would block
# unrelated `make` invocations (lint, format) and CI-entrypoint
# targets whose own recipe initializes the submodules before
# sub-making dev-image.
.PHONY: _dev-container-check-required-paths
_dev-container-check-required-paths:
	@missing="$(strip $(foreach p,$(DEV_CONTAINER_REQUIRED_PATHS),$(if $(wildcard $(DEV_CONTAINER_REPO_ROOT)/$(p)),,$(p))))"; \
	if [ -n "$$missing" ]; then \
	  echo "Missing required paths (did you init submodules?): $$missing" >&2; \
	  exit 1; \
	fi

.PHONY: dev-image dev-image-x86_64 dev-shell dev-image-tag \
        .devcontainer-initialize .devcontainer-fix-git-worktree \
        .devcontainer-stage-context .devcontainer-image-hash

dev-image dev-image-x86_64 dev-shell dev-image-tag \
.devcontainer-initialize .devcontainer-stage-context \
.devcontainer-image-hash: _dev-container-check-required-paths

# Stage the build context into a stable path under .devcontainer/.staged/.
# Invoked from VS Code's initializeCommand (so build.context = `.staged`
# gets the same narrow tree CI and `make dev-image` use) and from
# devcontainer.yml's CI job. Hash-computing local targets keep using a
# mktemp dir for parallel safety; this one writes to a stable path
# because VS Code (and CI's downstream buildx step) need one.
.devcontainer-stage-context:
	@rm -rf "$(_DEV_CONTAINER_STAGED)"
	@mkdir -p "$(_DEV_CONTAINER_STAGED)"
	@ctx="$(_DEV_CONTAINER_STAGED)"; $(_dev_container_stage_into_ctx)

# Print the 12-char hash of the already-staged .devcontainer/.staged/ tree.
# Caller must have run `make .devcontainer-stage-context` first. Used by
# devcontainer.yml so the tag is computed by the same code that the local
# Makefile uses.
.devcontainer-image-hash:
	@ctx="$(_DEV_CONTAINER_STAGED)"; \
	test -d "$$ctx" || { echo "ERROR: $$ctx not staged; run 'make .devcontainer-stage-context' first" >&2; exit 1; }; \
	$(_dev_container_compute_tag); \
	echo "$$tag"

# Host-side entrypoint for devcontainer.json. Besides staging the exact
# content-hashed context, expose the real Git common directory through an
# ignored symlink. The devcontainer mounts that link at /git-common; the
# post-start target below repairs linked-worktree gitdir pointers without
# copying metadata or exposing sibling worktrees.
#
# On a registry hit, replace only the staged Dockerfile with a one-line FROM
# of the immutable OCI image. devcontainer up then starts from the exact image
# CI built instead of recompiling the toolchain. A miss keeps the original
# staged Dockerfile, preserving the normal local-build fallback.
.devcontainer-initialize: .devcontainer-stage-context
	@git_common=$$(cd "$(DEV_CONTAINER_REPO_ROOT)" && git rev-parse --path-format=absolute --git-common-dir); \
	rm -f "$(_DEV_CONTAINER_GIT_COMMON_LINK)"; \
	ln -s "$$git_common" "$(_DEV_CONTAINER_GIT_COMMON_LINK)"; \
	rm -f "$(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref"; \
	ctx="$(_DEV_CONTAINER_STAGED)"; \
	$(_dev_container_compute_tag); \
	ref="$(DEV_CONTAINER_IMAGE_NAME):$(_DEV_CONTAINER_NATIVE_TAG_PREFIX)$$tag"; \
	if docker pull --platform "$(_DEV_CONTAINER_PLATFORM)" "$$ref" >/dev/null 2>&1; then \
	  printf 'FROM %s\n' "$$ref" > "$$ctx/.devcontainer/Dockerfile"; \
	  printf '%s\n' "$$ref" > "$(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref"; \
	  echo "Devcontainer cache hit: $$ref"; \
	else \
	  echo "Devcontainer cache miss: $$ref; building the staged Dockerfile locally"; \
	fi

# Container-side half of linked-worktree support. A worktree's .git file and
# submodule gitfiles point outside the relocated workspace. For every pointer
# rooted under a worktrees/ directory, create the missing container-only
# common-dir symlink to /git-common. Ordinary clones have a .git directory and
# take the no-op path.
.devcontainer-fix-git-worktree:
	@if [ -f "$(DEV_CONTAINER_REPO_ROOT)/.git" ]; then \
	  find "$(DEV_CONTAINER_REPO_ROOT)" -name .git -type f -print0 | \
	  while IFS= read -r -d '' git_file; do \
	    git_dir=$$(sed -n 's/^gitdir: //p' "$$git_file"); \
	    [ -n "$$git_dir" ] || continue; \
	    case "$$git_dir" in \
	      /*) resolved="$$git_dir" ;; \
	      *) resolved=$$(realpath -m "$$(dirname "$$git_file")/$$git_dir") ;; \
	    esac; \
	    case "$$resolved" in \
	      */worktrees/*) \
	        common_link=$${resolved%%/worktrees/*}; \
	        if [ ! -e "$$common_link" ]; then \
	          mkdir -p "$$(dirname "$$common_link")"; \
	          ln -s /git-common "$$common_link"; \
	        fi ;; \
	    esac; \
	  done; \
	fi

# Print the full image:tag that would be used. Useful for debugging.
# Works inside or outside a container (no docker required).
dev-image-tag:
	@$(_dev_container_stage_context); \
	$(_dev_container_compute_tag); \
	echo "$(DEV_CONTAINER_IMAGE_NAME):$(_DEV_CONTAINER_NATIVE_TAG_PREFIX)$$tag"

# Shared mounts for any in-container invocation: the repo root, plus the
# git common dir when running inside a worktree (so `git` works).
_DEV_CONTAINER_MOUNTS := \
  -v $(DEV_CONTAINER_REPO_ROOT):$(DEV_CONTAINER_REPO_ROOT) \
  $(_DEV_CONTAINER_WORKTREE_MOUNT) \
  -w $(DEV_CONTAINER_REPO_ROOT)

# Public: prefix for running a scripted command in the devcontainer image.
# Includes the resolved image ref and `-i` (so stdin pipes work) but no
# `-t` (so it works under `make` / CI without a TTY). Usage:
#   foo: dev-image
#   	$(IN_DEVCONTAINER) cmd args
# When `make` is invoked from inside a container, IN_DEVCONTAINER is empty,
# so the command runs in-place — same recipe works inside or outside.
IN_DEVCONTAINER ?= docker run --rm -i $(_DEV_CONTAINER_MOUNTS) \
  $$(cat $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref)

# linux/amd64 variant: same shape as IN_DEVCONTAINER but pinned to amd64,
# for running cross-compiled x86_64 binaries (e.g. Windows test exes under
# wine64) on any host. On Apple Silicon, Docker emulates via Rosetta. On
# native amd64 the platform pin is a no-op and we reuse the regular image.
_DEV_CONTAINER_X86_64_IMAGE_REF_FILE := $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref-x86_64
IN_DEVCONTAINER_X86_64 ?= docker run --rm -i --platform=linux/amd64 $(_DEV_CONTAINER_MOUNTS) \
  $$(cat $(_DEV_CONTAINER_X86_64_IMAGE_REF_FILE))

ifeq ($(_DEV_CONTAINER_INSIDE),1)
  IN_DEVCONTAINER :=
  IN_DEVCONTAINER_X86_64 :=
endif

# Targets whose behaviour differs inside vs outside a container.
# Inside: dev-image is a no-op (already running on it); dev-shell fails
# loudly because there's no docker daemon.
ifeq ($(_DEV_CONTAINER_INSIDE),1)

dev-image dev-image-x86_64:
	@:

dev-shell:
	@echo "make dev-shell: already inside the devcontainer; run /bin/sh directly" >&2; exit 1

else # _DEV_CONTAINER_INSIDE

# Pull the image if available; otherwise build locally from the staged context.
dev-image:
	@$(_dev_container_stage_context); \
	$(_dev_container_compute_tag); \
	ref="$(DEV_CONTAINER_IMAGE_NAME):$(_DEV_CONTAINER_NATIVE_TAG_PREFIX)$$tag"; \
	if docker pull --platform "$(_DEV_CONTAINER_PLATFORM)" "$$ref" >/dev/null 2>&1; then \
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

# Build the linux/amd64 variant. On amd64 hosts this reuses dev-image; on
# arm64 hosts it produces a separate `:<tag>-x86_64` image so it doesn't
# clobber the native one — built locally only (CI doesn't publish the
# `-x86_64` ref), so no docker pull attempt. Buildx caches per-platform
# so repeats are cheap.
ifeq ($(_DEV_CONTAINER_PLATFORM),linux/amd64)
dev-image-x86_64: dev-image
	@cp $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref $(_DEV_CONTAINER_X86_64_IMAGE_REF_FILE)
else
dev-image-x86_64:
	@$(_dev_container_stage_context); \
	$(_dev_container_compute_tag); \
	registry_ref="$(DEV_CONTAINER_IMAGE_NAME):$(_DEV_CONTAINER_AMD64_TAG_PREFIX)$$tag"; \
	if docker pull --platform=linux/amd64 "$$registry_ref" >/dev/null 2>&1; then \
	  ref="$$registry_ref"; \
	  echo "Pulled $$ref"; \
	else \
	  ref="$(DEV_CONTAINER_IMAGE_NAME):$$tag-x86_64"; \
	  docker buildx build --platform=linux/amd64 \
	    --file "$$ctx/.devcontainer/Dockerfile" \
	    --build-context repo="$$ctx" \
	    --build-arg ARCH=x86_64 \
	    $(DOCKER_BUILDX_FLAGS) \
	    --load -t "$$ref" \
	    "$$ctx"; \
	fi; \
	echo "$$ref" > $(_DEV_CONTAINER_X86_64_IMAGE_REF_FILE)
endif

dev-shell: dev-image
	@ref=$$(cat $(DEV_CONTAINER_REPO_ROOT)/.devcontainer/.image-ref); \
	docker run --rm -it $(_DEV_CONTAINER_MOUNTS) "$$ref" /bin/sh

endif # _DEV_CONTAINER_INSIDE
