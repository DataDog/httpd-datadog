#!/bin/sh
set -eu

: "${DEVCONTAINER_IMAGE_AMD64:?Missing plain amd64 OCI image}"
: "${CI_IMAGE_HASH:?Missing devcontainer content hash}"
: "${DEVCONTAINER_PUBLIC_IMAGE:?Missing public image name}"

image_ref="${DEVCONTAINER_PUBLIC_IMAGE}:${CI_IMAGE_HASH}"
status=$(curl --silent --show-error --location --head \
  --connect-timeout 10 --max-time 60 \
  --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
  --output /dev/null --write-out '%{http_code}' \
  "https://registry.datadoghq.com/v2/${DEVCONTAINER_PUBLIC_IMAGE}/manifests/${CI_IMAGE_HASH}")

case "$status" in
  200) echo "Public image cache hit: $image_ref" ;;
  404)
    dd-pkg publish-image \
      --timeout 1800 --poll-interval 30 \
      --registries dev --signing=false \
      --sources "$DEVCONTAINER_IMAGE_AMD64" \
      --destinations "$image_ref" \
      --merge-strategy none
    ;;
  *) echo "ERROR: public image lookup returned HTTP $status" >&2; exit 1 ;;
esac

dd-pkg publish-image \
  --timeout 1800 --poll-interval 30 \
  --registries dev --signing=false \
  --tag-reference "$image_ref" \
  --new-tags main
