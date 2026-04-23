#!/usr/bin/env bash
# DO NOT EDIT. Synced from DataDog/libdatadog-build by the
# libdatadog-build repository-tools campaigner — edits here will be
# overwritten on the next run.
#
# Runs the content-addressed mirror_images.py from libdatadog-build
# against this repo's mirror_images.yaml. The URL below is a content-
# hash pin updated on each campaigner sync; uv reads the script's
# inline-metadata header and runs it in an ephemeral venv, so no
# Python setup is needed.
#
# Usage: ./mirror-images.sh <lock|mirror|lint|add|relock> [args...]
set -euo pipefail

readonly MIRROR_IMAGES_URL="https://gitlab-templates.ddbuild.io/libdatadog/repository-tools/ca/a2cd812382016164dce1af42d5e80cf4a8dfd1bd98af32bd1a1b6b8aade223f5/scripts/mirror-images/mirror_images.py"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL --output "$tmp/mirror_images.py" "$MIRROR_IMAGES_URL"
exec uv run "$tmp/mirror_images.py" "$@"
