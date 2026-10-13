#!/usr/bin/env bash
# Run clang-tidy in the CI container.
#
# Configures CMake with preset ci-dev, then run-clang-tidy -p on
# mod_datadog/src/ so tidy uses that compile_commands.json.
#
# Usage:
#   make lint-tidy
#   ./scripts/clang-tidy.sh

set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
cd "$repo_root"

in_container() {
    [[ -f /.dockerenv ]] || [[ -n "${KUBERNETES_SERVICE_HOST:-}" ]] || \
        [[ "${HTTPD_DATADOG_TIDY_IN_CONTAINER:-}" == "1" ]]
}

if ! in_container; then
    exec make -C "$repo_root" lint-tidy
fi

build_dir=${BUILD_DIR:-.clang-tidy-build}
# Alpine LLVM layout (no hyphen), same major as the image toolchain.
llvm_major_version=$(clang -dumpversion | cut -d. -f1)
llvm_bin=/usr/lib/llvm${llvm_major_version}/bin
clang_tidy=$llvm_bin/clang-tidy
run_clang_tidy=$llvm_bin/run-clang-tidy

if [[ ! -x "$clang_tidy" ]]; then
    apk add --no-cache clang-extra-tools
fi

if [[ ! -x "$clang_tidy" ]]; then
    >&2 echo "$clang_tidy is required (pinned)."
    exit 1
fi

if [[ ! -x "$run_clang_tidy" && -x /usr/bin/run-clang-tidy ]]; then
    # Alpine ships the runner unversioned; -clang-tidy-binary stays pinned.
    run_clang_tidy=/usr/bin/run-clang-tidy
fi

if [[ ! -x "$run_clang_tidy" ]]; then
    >&2 echo "$llvm_bin/run-clang-tidy is required (pinned)."
    exit 1
fi

git config --global --add safe.directory "$repo_root" >/dev/null 2>&1 || true
if [[ ! -f deps/dd-trace-cpp/CMakeLists.txt ]] || [[ ! -f deps/nginx-datadog/CMakeLists.txt ]]; then
    git submodule update --init --depth=1 deps/dd-trace-cpp deps/nginx-datadog
fi

cmake --fresh --preset=ci-dev -B "$build_dir" \
    -DCMAKE_TOOLCHAIN_FILE="/sysroot/$(uname -m)-none-linux-musl/Toolchain.cmake" .

python3 - "$build_dir/compile_commands.json" "$repo_root" <<'PY'
import json, os, sys
db_path, root = sys.argv[1], sys.argv[2]
verified_source_count = 0
for entry in json.load(open(db_path)):
    path = entry.get("file") or ""
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(entry.get("directory", root), path))
    relative_path = os.path.relpath(path, root)
    if not relative_path.startswith("mod_datadog/src/"):
        continue
    if not relative_path.endswith((".c", ".cc", ".cpp", ".cxx")):
        continue
    command = entry.get("command") or ""
    if "/sysroot" not in command:
        sys.stderr.write(
            "BUILD_DIR was not configured with preset ci-dev; refusing to run tidy.\n"
            "  missing /sysroot in " + relative_path + "\n"
        )
        sys.exit(1)
    verified_source_count += 1
if verified_source_count == 0:
    sys.stderr.write("No mod_datadog/src/ entries in " + db_path + ".\n")
    sys.exit(1)
PY

if ! echo '#include <string>' | "$llvm_bin/clang++" -stdlib=libc++ -x c++ - -fsyntax-only; then
    >&2 echo "C++ headers are not usable with $llvm_bin/clang++; refusing to run tidy."
    exit 1
fi

"$run_clang_tidy" -p "$build_dir" -clang-tidy-binary "$clang_tidy" \
    -header-filter "^$repo_root/mod_datadog/src/" -quiet \
    "^$repo_root/mod_datadog/src/"
