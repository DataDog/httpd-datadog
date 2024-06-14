#!/usr/bin/env bash
set -euo pipefail
# Enforce codestyle on the codebase

usage() {
  cat<<'END_USAGE'
codestyle.sh - Enforce codestyle on the codebase

usage:
  codestyle.sh [-h] {lint, format}

options:
  -h, --help              Show this help messge and exit

subcommand:
  lint: 
  format: Format in-place
END_USAGE
}

CLANG_ARG=""
CONTINUE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    format)
      CLANG_ARG="-i"
      shift
      ;;
    lint)
      CLANG_ARG="--Werror --dry-run"
      shift
      ;;
    *)
      usage
      exit 1
  esac
done

if [[ -z "$CLANG_ARG" ]]; then
  >&2 echo "Missing subcommand"
  usage
  exit 1
fi

find mod_datadog/ -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-14 ${CLANG_ARG} --style=file
