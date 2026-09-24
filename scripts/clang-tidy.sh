#!/usr/bin/env bash
# Run clang-tidy on first-party C++ sources. Findings fail the check.
#
# Requires compile_commands.json. Generate it with:
#   cmake --preset=ci-dev -B build .
# or locally:
#   cmake -B build -DHTTPD_SRC_DIR=httpd .

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

build_dir=${BUILD_DIR:-build}
compile_commands="$build_dir/compile_commands.json"

find_tidy() {
    if command -v clang-tidy >/dev/null 2>&1; then
        echo clang-tidy
        return
    fi
    local candidate
    for candidate in clang-tidy-21 clang-tidy-20 clang-tidy-19 clang-tidy-18 \
                     clang-tidy-17 clang-tidy-16 clang-tidy-15 clang-tidy-14; do
        if command -v "$candidate" >/dev/null 2>&1; then
            echo "$candidate"
            return
        fi
    done
    return 1
}

if ! [[ -f "$compile_commands" ]]; then
    >&2 echo "Missing $compile_commands."
    >&2 echo "Configure CMake first so clang-tidy can use the compilation database:"
    >&2 echo "  cmake --preset=ci-dev -B ${build_dir} ."
    >&2 echo "  ./scripts/clang-tidy.sh"
    exit 1
fi

if ! tidy=$(find_tidy); then
    >&2 echo "clang-tidy is not installed. On Alpine: apk add clang-extra-tools"
    exit 1
fi

mapfile -t files < <(find mod_datadog/ test/unit-test/ \
    -type f \( -name '*.cpp' -o -name '*.c' \))

if [[ ${#files[@]} -eq 0 ]]; then
    >&2 echo "No C/C++ sources found to analyze."
    exit 1
fi

"$tidy" -p "$build_dir" --quiet --use-color \
    -extra-arg=-Wno-error \
    -extra-arg=-Wno-unknown-warning-option \
    -extra-arg=-Wno-unused-command-line-argument \
    "${files[@]}"
