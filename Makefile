COMMIT_SHA ?= $(shell git rev-parse --short HEAD)
DOCKER_REPO ?= datadog/docker-library

.PHONY: push-ci-images
push-ci-images:
	docker build --progress=plain --platform linux/amd64 -t $(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)-amd64 .
	docker push $(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)-amd64
	docker build --progress=plain --platform linux/arm64 -t $(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)-arm64 .
	docker push $(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)-arm64
	docker buildx imagetools create -t $(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA) \
			$(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)-amd64 \
			$(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)-arm64
	docker push $(DOCKER_REPO):httpd-datadog-ci-2.4-$(COMMIT_SHA)
