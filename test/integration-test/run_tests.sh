#!/usr/bin/env bash
#
# Convenience script to run integration tests with uv
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Default paths - override with environment variables
HTTPD_BIN_PATH="${HTTPD_BIN_PATH:-}"
HTTPD_MODULE_PATH="${HTTPD_MODULE_PATH:-}"

# Parse command line arguments
PYTEST_ARGS=()
TEST_PATH="scenarios/"

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS] [TEST_PATH]

Run integration tests for httpd-datadog module using uv.

OPTIONS:
    -b, --bin-path PATH         Path to apachectl binary (required)
    -m, --module-path PATH      Path to mod_datadog.so (required)
    -l, --log-dir PATH          Directory for test logs
    -v, --verbose               Increase verbosity (-v, -vv, -vvv)
    -s, --show-output           Show print statements and logs
    -k EXPRESSION               Run tests matching expression
    -x, --exitfirst             Exit on first failure
    --pdb                       Drop into debugger on failures
    --markers MARKER            Run tests with specific marker (smoke, ci)
    -h, --help                  Show this help message

EXAMPLES:
    # Run all tests
    $0 -b /usr/local/bin/apachectl -m /path/to/mod_datadog.so

    # Run specific test file
    $0 -b /usr/local/bin/apachectl -m /path/to/mod_datadog.so scenarios/test_rum.py

    # Run specific test
    $0 -b /usr/local/bin/apachectl -m /path/to/mod_datadog.so -k test_rum_selective_disabling

    # Run with verbose output
    $0 -b /usr/local/bin/apachectl -m /path/to/mod_datadog.so -vv -s

    # Run only smoke tests
    $0 -b /usr/local/bin/apachectl -m /path/to/mod_datadog.so --markers smoke

ENVIRONMENT VARIABLES:
    HTTPD_BIN_PATH              Default path to apachectl
    HTTPD_MODULE_PATH           Default path to mod_datadog.so

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--bin-path)
            HTTPD_BIN_PATH="$2"
            shift 2
            ;;
        -m|--module-path)
            HTTPD_MODULE_PATH="$2"
            shift 2
            ;;
        -l|--log-dir)
            PYTEST_ARGS+=("--log-dir=$2")
            shift 2
            ;;
        -v|--verbose)
            PYTEST_ARGS+=("-v")
            shift
            ;;
        -vv)
            PYTEST_ARGS+=("-vv")
            shift
            ;;
        -vvv)
            PYTEST_ARGS+=("-vvv")
            shift
            ;;
        -s|--show-output)
            PYTEST_ARGS+=("-s")
            shift
            ;;
        -k)
            PYTEST_ARGS+=("-k" "$2")
            shift 2
            ;;
        -x|--exitfirst)
            PYTEST_ARGS+=("-x")
            shift
            ;;
        --pdb)
            PYTEST_ARGS+=("--pdb")
            shift
            ;;
        --markers)
            PYTEST_ARGS+=("-m" "$2")
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            # Treat as test path
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Validate required parameters
if [ -z "$HTTPD_BIN_PATH" ]; then
    echo -e "${RED}Error: Apache binary path is required${NC}"
    echo "Set with -b/--bin-path or HTTPD_BIN_PATH environment variable"
    echo ""
    show_usage
    exit 1
fi

if [ -z "$HTTPD_MODULE_PATH" ]; then
    echo -e "${RED}Error: Module path is required${NC}"
    echo "Set with -m/--module-path or HTTPD_MODULE_PATH environment variable"
    echo ""
    show_usage
    exit 1
fi

# Validate paths exist
if [ ! -f "$HTTPD_BIN_PATH" ]; then
    echo -e "${RED}Error: Apache binary not found: $HTTPD_BIN_PATH${NC}"
    exit 1
fi

if [ ! -f "$HTTPD_MODULE_PATH" ]; then
    echo -e "${RED}Error: Module not found: $HTTPD_MODULE_PATH${NC}"
    exit 1
fi

echo -e "${GREEN}Starting integration tests...${NC}"
echo "Apache binary: $HTTPD_BIN_PATH"
echo "Module path: $HTTPD_MODULE_PATH"
echo "Test path: $TEST_PATH"
echo ""

# Ensure dependencies are synced
echo -e "${YELLOW}Syncing dependencies with uv...${NC}"
uv sync

echo ""
echo -e "${GREEN}Running tests...${NC}"
echo ""

# Run pytest with uv
uv run pytest "$TEST_PATH" \
    --bin-path="$HTTPD_BIN_PATH" \
    --module-path="$HTTPD_MODULE_PATH" \
    "${PYTEST_ARGS[@]}"

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Tests failed with exit code $exit_code${NC}"
fi

exit $exit_code
