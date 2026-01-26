.PHONY: help install test test-rum test-smoke test-ci clean

# Default target
help:
	@echo "Available targets:"
	@echo "  install       - Install dependencies using uv"
	@echo "  test          - Run all tests"
	@echo "  test-rum      - Run RUM tests only"
	@echo "  test-smoke    - Run smoke tests only"
	@echo "  test-ci       - Run CI tests only"
	@echo "  clean         - Clean up test artifacts"
	@echo ""
	@echo "Required environment variables:"
	@echo "  HTTPD_BIN_PATH      - Path to apachectl binary"
	@echo "  HTTPD_MODULE_PATH   - Path to mod_datadog.so"
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
	@./run_tests.sh

# Run RUM tests only
test-rum:
	@./run_tests.sh scenarios/test_rum.py

# Run smoke tests
test-smoke:
	@./run_tests.sh --markers smoke

# Run CI tests
test-ci:
	@./run_tests.sh --markers ci

# Run with verbose output
test-verbose:
	@./run_tests.sh -vv -s

# Clean up test artifacts
clean:
	@echo "Cleaning up test artifacts..."
	rm -rf .venv/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	rm -rf scenarios/__pycache__/
	rm -rf log-*/
	rm -f uv.lock
	@echo "Done!"
