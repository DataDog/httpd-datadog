#!/bin/sh
# Build mod_datadog (with RUM) and run the full integration-test suite.
# Assumes it runs inside the devcontainer image (Alpine + musl sysroot + httpd
# at /httpd/httpd-build/ + uv).
set -eux

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ARCH="$(uname -m)"

# Use a container-specific build tree to avoid colliding with host builds
# (host cmake would use Unix Makefiles; the ci-release preset uses Ninja).
BUILD_DIR="$REPO_ROOT/build-container"
DIST_DIR="$REPO_ROOT/dist-container"

# Repo root is bind-mounted from the host; cmake complains otherwise.
git config --global --add safe.directory "$REPO_ROOT"

cmake --preset=ci-release \
	-DHTTPD_DATADOG_ENABLE_RUM=ON \
	-DCMAKE_TOOLCHAIN_FILE="/sysroot/${ARCH}-none-linux-musl/Toolchain.cmake" \
	-B "$BUILD_DIR" .
cmake --build "$BUILD_DIR" -j
cmake --install "$BUILD_DIR" --prefix "$DIST_DIR"

cd test/integration-test

# Keep the venv outside the bind-mounted repo so a host-side `uv sync`
# (darwin/arm64 wheels) can't shadow the container's Linux one.
export UV_PROJECT_ENVIRONMENT=/root/.venv-httpd-datadog-tests

uv sync

# Pytest's early arg parser runs BEFORE conftest registers `--bin-path`.
# If we pass `--bin-path VALUE` (space-separated), that parser treats the
# value as a positional test path and uses its parent as rootdir, which
# then prevents conftest from loading. The `=` syntax keeps the option and
# its value in a single token and avoids that race.
uv run pytest \
	--bin-path=/httpd/httpd-build/bin/apachectl \
	--module-path="$DIST_DIR/lib/mod_datadog.so" \
	--log-dir="$REPO_ROOT/logs" \
	-v "$@"
