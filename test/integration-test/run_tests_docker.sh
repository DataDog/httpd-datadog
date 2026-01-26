#!/usr/bin/env bash
#
# Run integration tests in Docker (matching CI environment)
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DOCKER_IMAGE="datadog/docker-library:httpd-datadog-ci-2.4-cdb3cb2"

# Check if RUM tests are being run
ENABLE_RUM="OFF"
for arg in "$@"; do
    if [[ "$arg" == *"test_rum"* ]] || [[ "$arg" == *"rum"* ]]; then
        ENABLE_RUM="ON"
        echo -e "${YELLOW}RUM tests detected - enabling RUM support in build${NC}"
        break
    fi
done

echo -e "${GREEN}Building mod_datadog.so in Docker...${NC}"

# Build the module in Docker
docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    -e "ENABLE_RUM=$ENABLE_RUM" \
    "$DOCKER_IMAGE" \
    sh -c '
        set -e
        git config --global --add safe.directory /workspace
        git submodule update --init --recursive

        # Detect architecture and set toolchain
        ARCH=$(uname -m)
        if [ "$ARCH" = "aarch64" ]; then
            TOOLCHAIN="/sysroot/aarch64-none-linux-musl/Toolchain.cmake"
        else
            TOOLCHAIN="/sysroot/x86_64-none-linux-musl/Toolchain.cmake"
        fi

        cmake -B build \
            -G Ninja \
            -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN" \
            -DHTTPD_SRC_DIR=/httpd \
            -DCMAKE_BUILD_TYPE=Debug \
            -DHTTPD_DATADOG_ENABLE_COVERAGE=1 \
            -DHTTPD_DATADOG_PATCH_AWAY_LIBC=1 \
            -DHTTPD_DATADOG_ENABLE_RUM=$ENABLE_RUM \
            .
        cmake --build build -j
        cmake --install build --prefix dist
    '

if [ ! -f "$PROJECT_ROOT/dist/lib/mod_datadog.so" ]; then
    echo -e "${RED}Error: Module build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Module built successfully${NC}"
echo -e "${GREEN}Running integration tests in Docker...${NC}"
echo ""

# Install Python dependencies and run tests
docker run --rm \
    -v "$PROJECT_ROOT:/workspace" \
    -w /workspace \
    "$DOCKER_IMAGE" \
    sh -c "
        set -e
        pip install -r requirements.txt --break-system-packages
        pytest test/integration-test/scenarios/ \
            --module-path dist/lib/mod_datadog.so \
            --bin-path /httpd/httpd-build/bin/apachectl \
            --log-dir /workspace/test-logs \
            -v \
            $@
    "

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Tests failed with exit code $exit_code${NC}"
fi

exit $exit_code
