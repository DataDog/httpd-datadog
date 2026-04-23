#!/usr/bin/env bash
# DO NOT EDIT. Synced from DataDog/libdatadog-build by the
# libdatadog-build repository-tools campaigner — edits here will be
# overwritten on the next run.
#
# Runs the content-addressed mirror_images.py from libdatadog-build
# against this repo's mirror_images.yaml. The URL below is a content-
# hash pin updated on each campaigner sync; `uv run --script <URL>`
# fetches and executes it in one call, reading the script's inline
# metadata header for deps — no Python setup needed.
#
# Usage: ./mirror-images.sh <lock|mirror|lint|add|relock> [args...]
exec uv run --script "https://gitlab-templates.ddbuild.io/libdatadog/repository-tools/ca/a836d61111dddd120eceb6e6e283ed5e7d3a131d3830a1186683422c7a44a86a/scripts/mirror-images/mirror_images.py" "$@"
