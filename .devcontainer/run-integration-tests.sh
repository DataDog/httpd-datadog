#!/bin/sh
set -eu

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

module_path=${MODULE_PATH:-}
case "$module_path" in
  ""|/*) ;;
  *) module_path="$repo_root/$module_path" ;;
esac

git config --global --add safe.directory "$repo_root"

if [ -z "$module_path" ]; then
  arch=$(uname -m)
  build_dir="$repo_root/build-container"
  dist_dir="$repo_root/dist-container"
  cmake --preset=ci-release \
    -DHTTPD_DATADOG_ENABLE_RUM=ON \
    -DCMAKE_TOOLCHAIN_FILE="/sysroot/${arch}-none-linux-musl/Toolchain.cmake" \
    -B "$build_dir" .
  cmake --build "$build_dir" -j
  # Keep the build tree for incremental compiles; refresh installed outputs.
  rm -rf "$dist_dir"
  cmake --install "$build_dir" --prefix "$dist_dir"
  module_path="$dist_dir/lib/mod_datadog.so"
fi

cd "$repo_root/test/integration-test"
export UV_PROJECT_ENVIRONMENT="$HOME/.venv-httpd-datadog-tests"
uv sync --locked

# The equals form keeps pytest's early parser from treating values as paths.
uv run pytest \
  --bin-path=/httpd/httpd-build/bin/apachectl \
  --module-path="$module_path" \
  --log-dir="$repo_root/logs" \
  -v "$@"
