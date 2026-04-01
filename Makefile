# The CI image used for some GitHub jobs is built by the GitLab build-ci-image job.
# The hash is computed by this GitLab job from the files used to build the image.
#
# Whenever this image needs to be updated, one should:
#   - Get the hash from a run of the GitLab build-ci-image job.
#   - Copy this hash here, and in the GitHub workflow files.
#   - Run: make replicate-ci-image-for-github.

CI_DOCKER_IMAGE_HASH ?= 28219c0ef3e00f1e3d5afcab61a73a5e9bd2a9b957d7545556711cce2a6262cd
CI_IMAGE_FROM_GITLAB ?= registry.ddbuild.io/ci/httpd-datadog/amd64:$(CI_DOCKER_IMAGE_HASH)
CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB ?= datadog/docker-library:httpd-datadog-ci-$(CI_DOCKER_IMAGE_HASH)

# Architecture detection for local Docker targets.
# Maps host arch to CI image tag and toolchain path.
UNAME_ARCH := $(shell uname -m)
ifeq ($(UNAME_ARCH),arm64)
  CI_ARCH ?= arm64
  TOOLCHAIN_ARCH ?= aarch64
else
  CI_ARCH ?= amd64
  TOOLCHAIN_ARCH ?= x86_64
endif
CI_IMAGE ?= registry.ddbuild.io/ci/httpd-datadog/$(CI_ARCH):$(CI_DOCKER_IMAGE_HASH)

VENDOR_DIR ?= $(PWD)/.deps
DOCKER_RUN = docker run --rm -v $(PWD):/src -w /src $(CI_IMAGE)
DOCKER_RUN_IT = docker run --rm -it -v $(PWD):/src -w /src $(CI_IMAGE)
DOCKER_GIT_SAFE = git config --global --add safe.directory /src
DOCKER_CMAKE_ARGS = -DCMAKE_TOOLCHAIN_FILE=/sysroot/$(TOOLCHAIN_ARCH)-none-linux-musl/Toolchain.cmake -DHTTPD_SRC_DIR=/httpd -DHTTPD_DATADOG_PATCH_AWAY_LIBC=1
DOCKER_VENDOR_ARGS = -DFETCHCONTENT_SOURCE_DIR_CORROSION=/src/.deps/corrosion -DFETCHCONTENT_SOURCE_DIR_INJECTBROWSERSDK=/src/.deps/inject-browser-sdk

.PHONY: replicate-ci-image-for-github
replicate-ci-image-for-github:
	docker pull $(CI_IMAGE_FROM_GITLAB)
	docker tag $(CI_IMAGE_FROM_GITLAB) $(CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB)
	docker push $(CI_IMAGE_IN_PUBLIC_REPO_FOR_GITHUB)

.PHONY: vendor
vendor:
	cmake -DVENDOR_DIR=$(VENDOR_DIR) -P scripts/prefetch-deps.cmake

.PHONY: docker-shell
docker-shell:
	$(DOCKER_RUN_IT) sh

.PHONY: docker-build
docker-build:
	$(DOCKER_RUN) sh -c '$(DOCKER_GIT_SAFE) && \
		cmake -B build $(DOCKER_CMAKE_ARGS) -G Ninja . && \
		cmake --build build -j'

.PHONY: docker-build-rum
docker-build-rum: vendor
	$(DOCKER_RUN) sh -c '$(DOCKER_GIT_SAFE) && \
		cmake -B build-rum $(DOCKER_CMAKE_ARGS) $(DOCKER_VENDOR_ARGS) -DHTTPD_DATADOG_ENABLE_RUM=ON -G Ninja . && \
		cmake --build build-rum -j'

.PHONY: docker-test
docker-test: docker-build
	$(DOCKER_RUN) sh -c '$(DOCKER_GIT_SAFE) && \
		cd test/integration-test && uv sync && \
		uv run pytest scenarios \
			--module-path /src/build/mod_datadog/mod_datadog.so \
			--bin-path /httpd/httpd-build/bin/apachectl \
			--log-dir /src/logs -m "not requires_rum" -v'

.PHONY: docker-test-rum
docker-test-rum: docker-build-rum
	$(DOCKER_RUN) sh -c '$(DOCKER_GIT_SAFE) && \
		cd test/integration-test && uv sync && \
		uv run pytest scenarios \
			--module-path /src/build-rum/mod_datadog/mod_datadog.so \
			--bin-path /httpd/httpd-build/bin/apachectl \
			--log-dir /src/logs -m requires_rum -v'
