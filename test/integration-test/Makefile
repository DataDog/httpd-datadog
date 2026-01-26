.PHONY: help install test test-rum test-smoke test-ci test-verbose clean

# Default target
help:
	@echo "Available targets:"
	@echo "  install       - Install dependencies using uv"
	@echo "  test          - Run all tests"
	@echo "  test-rum      - Run RUM tests only"
	@echo "  test-smoke    - Run smoke tests only"
	@echo "  test-ci       - Run CI tests only"
	@echo "  test-verbose  - Run tests with verbose output"
	@echo "  clean         - Clean up test artifacts"
	@echo ""
	@echo "Required environment variables:"
	@echo "  HTTPD_BIN_PATH      - Path to apachectl binary"
	@echo "  HTTPD_MODULE_PATH   - Path to mod_datadog.so"
	@echo ""
	@echo "Optional environment variables:"
	@echo "  TEST_LOG_DIR        - Directory for test logs (default: auto-generated)"
	@echo ""
	@echo "Example:"
	@echo "  export HTTPD_BIN_PATH=/usr/local/bin/apachectl"
	@echo "  export HTTPD_MODULE_PATH=/path/to/mod_datadog.so"
	@echo "  make test"

# Install dependencies
install:
	@echo "Installing dependencies with uv..."
	uv sync
	@echo "Done!"

# Run all tests
test:
	uv run pytest

# Run RUM tests only
test-rum:
	uv run pytest scenarios/test_rum.py -v

# Run smoke tests
test-smoke:
	uv run pytest -m smoke

# Run CI tests
test-ci:
	uv run pytest -m ci

# Run with verbose output
test-verbose:
	uv run pytest -vv -s

# Clean up test artifacts
clean:
	@echo "Cleaning up test artifacts..."
	rm -rf .venv/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	rm -rf scenarios/__pycache__/
	rm -rf pytest_plugins/__pycache__/
	rm -rf log-*/
	rm -rf test-logs/
	rm -f .coverage
	rm -f *.profraw
	@echo "Done!"
