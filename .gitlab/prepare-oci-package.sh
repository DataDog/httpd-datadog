#!/bin/bash

# Called by one-pipeline's package-oci job to populate the sources/ directory
# that `datadog-package create` expects.
#
# package-oci creates a packaging/ subdirectory of the repo root and cds into
# it before exec'ing this script, so ../artifacts/ resolves to the ssi-build
# artifacts and sources/ already contains the checked-in requirements.json.

set -euo pipefail

if [ -z "${ARCH:-}" ]; then
  echo "ERROR: ARCH not available as an environment variable"
  exit 1
fi

# package-oci is a linux/windows x amd64/arm64 matrix. There is no Windows
# build of mod_datadog, so leave sources/ untouched: package-oci skips package
# creation when sources/ is empty.
if [ "${OS:-}" = "windows" ]; then
  echo "httpd-datadog does not support Windows. Skipping."
  exit 0
fi

SOURCES_DIR="../artifacts/ssi-sources/${ARCH}"

if [ ! -d "${SOURCES_DIR}" ]; then
  echo "ERROR: sources directory not found: ${SOURCES_DIR} (pwd: $(pwd))"
  echo "The ssi-build:${ARCH} job must complete before package-oci runs."
  exit 1
fi

if [ -z "$(ls -A "${SOURCES_DIR}")" ]; then
  echo "ERROR: sources directory is empty: ${SOURCES_DIR}"
  exit 1
fi

echo "Copying sources from ${SOURCES_DIR} to sources/"
mkdir -p sources
cp -r "${SOURCES_DIR}/"* sources/

so_count=$(find sources -name '*.so' -type f | wc -l)
if [ "$so_count" -eq 0 ]; then
  echo "ERROR: no .so module files found in sources/ after copy from ${SOURCES_DIR}"
  exit 1
fi

echo "Sources contents:"
find sources -type f | sort
