#!/usr/bin/env bash
# Run the pinned clang-tidy through CMake in the httpd-datadog devcontainer.
#
# clang-tidy must use the same compiler, flags, and sysroot as the real
# build (ci-dev). CMake's CXX_CLANG_TIDY on mod_datadog does that: it
# invokes tidy with the exact compile line after `--`. Do not run tidy
# against a host compilation database.
#
# Usage:
#   make lint-tidy
#   ./scripts/clang-tidy.sh

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

# Must match LLVM_VERSION in .devcontainer/Dockerfile (major).
CLANG_TIDY_VERSION=17

in_container() {
    [[ -f /.dockerenv ]] || [[ -n "${KUBERNETES_SERVICE_HOST:-}" ]] || \
        [[ "${HTTPD_DATADOG_TIDY_IN_CONTAINER:-}" == "1" ]]
}

if ! in_container; then
    if ! command -v docker >/dev/null 2>&1; then
        >&2 echo "docker is required to run clang-tidy-${CLANG_TIDY_VERSION}."
        exit 1
    fi
    exec make -C "$REPO_ROOT" lint-tidy
fi

build_dir=${BUILD_DIR:-.clang-tidy-build}
tidy="clang-tidy-${CLANG_TIDY_VERSION}"

if ! command -v "$tidy" >/dev/null 2>&1 && command -v clang-tidy >/dev/null 2>&1; then
    found_major=$(clang-tidy --version | sed -n 's/.*version \([0-9][0-9]*\).*/\1/p' | head -n 1)
    if [[ "$found_major" == "$CLANG_TIDY_VERSION" ]]; then
        tidy=clang-tidy
    fi
fi

if ! command -v "$tidy" >/dev/null 2>&1; then
    apk add --no-cache clang-extra-tools
    if command -v clang-tidy >/dev/null 2>&1; then
        found_major=$(clang-tidy --version | sed -n 's/.*version \([0-9][0-9]*\).*/\1/p' | head -n 1)
        if [[ "$found_major" != "$CLANG_TIDY_VERSION" ]]; then
            >&2 echo "clang-tidy ${found_major} is installed, but ${CLANG_TIDY_VERSION} is pinned."
            exit 1
        fi
        tidy=clang-tidy
    fi
fi

if ! command -v "$tidy" >/dev/null 2>&1; then
    >&2 echo "clang-tidy-${CLANG_TIDY_VERSION} is required (pinned)."
    exit 1
fi

compiler=${CXX:-clang++}
if ! command -v "$compiler" >/dev/null 2>&1; then
    >&2 echo "$compiler is required (same toolchain as CMake)."
    exit 1
fi

compiler_major=$("$compiler" -dumpversion | cut -d. -f1)
tidy_major=$("$tidy" --version | sed -n 's/.*version \([0-9][0-9]*\).*/\1/p' | head -n 1)
if [[ "$compiler_major" != "$CLANG_TIDY_VERSION" || "$tidy_major" != "$CLANG_TIDY_VERSION" ]]; then
    >&2 echo "clang-tidy and the CMake compiler must both be LLVM ${CLANG_TIDY_VERSION}."
    >&2 echo "  ${compiler}: ${compiler_major}"
    >&2 echo "  ${tidy}: ${tidy_major}"
    exit 1
fi

git config --global --add safe.directory "$REPO_ROOT" >/dev/null 2>&1 || true
if [[ ! -f deps/dd-trace-cpp/CMakeLists.txt ]] || [[ ! -f deps/nginx-datadog/CMakeLists.txt ]]; then
    git submodule update --init --depth=1 deps/dd-trace-cpp deps/nginx-datadog
fi

# Reconfigure so CXX_CLANG_TIDY is attached to mod_datadog, then compile
# that target. CMake passes the exact ci-dev compile line to tidy.
# RUM is off in ci-dev, so rum/ is not a source of mod_datadog.
cmake --preset=ci-dev -B "$build_dir" . \
    -DHTTPD_DATADOG_ENABLE_CLANG_TIDY=ON \
    -DHTTPD_DATADOG_CLANG_TIDY="$tidy"

cmake --build "$build_dir" --target mod_datadog
