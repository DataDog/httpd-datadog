#!/usr/bin/env bash
# Run the pinned clang-tidy in the httpd-datadog devcontainer.
#
# clang-tidy is not reproducible across versions, and compile_commands.json
# points at this image's musl sysroot and /httpd. Do not run tidy against a
# host CMake database. Local invocations re-exec in the devcontainer, which
# configures CMake and then runs clang-tidy-17 (LLVM 17, same as the image).
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

git config --global --add safe.directory "$REPO_ROOT" >/dev/null 2>&1 || true
if [[ ! -f deps/dd-trace-cpp/CMakeLists.txt ]] || [[ ! -f deps/nginx-datadog/CMakeLists.txt ]]; then
    git submodule update --init --depth=1 deps/dd-trace-cpp deps/nginx-datadog
fi

if [[ ! -f "$build_dir/compile_commands.json" ]]; then
    cmake --preset=ci-dev -B "$build_dir" .
fi

# Only first-party module sources that this CMake configure actually built.
# ci-dev leaves RUM off, so rum/ has no compile-command entries — do not pass
# those files (clang-tidy would skip them and still exit 0).
mapfile -t files < <(python3 - "$build_dir/compile_commands.json" "$REPO_ROOT" <<'PY'
import json, os, sys
db_path, root = sys.argv[1], sys.argv[2]
includes = ("mod_datadog/src/",)
excludes = ("mod_datadog/src/rum/",)
seen = []
for ent in json.load(open(db_path)):
    path = ent.get("file") or ""
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(ent.get("directory", root), path))
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        continue
    if rel.startswith("..") or not rel.endswith((".c", ".cc", ".cpp", ".cxx")):
        continue
    if any(rel == e.rstrip("/") or rel.startswith(e) for e in excludes):
        continue
    if not any(rel.startswith(i) for i in includes):
        continue
    if path not in seen:
        seen.append(path)
for path in seen:
    print(path)
PY
)

if [[ ${#files[@]} -eq 0 ]]; then
    >&2 echo "No configured first-party sources (mod_datadog/src, excluding rum/) in $build_dir/compile_commands.json."
    exit 1
fi

"$tidy" -p "$build_dir" --quiet --use-color \
    -extra-arg=-Wno-error \
    -extra-arg=-Wno-unknown-warning-option \
    -extra-arg=-Wno-unused-command-line-argument \
    "${files[@]}"
