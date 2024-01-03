#!/bin/sh 
set -e
# Installation script for Datadog's httpd tracing module.
#
# It does:
#   - Attempt to detect your Linux distribution, CPU architecture and httpd version.
#   - Download the latest release of the module.
#   - Update your httpd configuration to load the module.
#
# Requirements:
#   - `root` or `sudo` privileges to run.
#
# Usage:
#
# To install and modify your httpd configuration:
#   ./install_module.sh [--version <VERSION>]
#
# To download the latest release module:
#   ./install_module.sh download [-o|--output-dir <DIR>] 
#
# To modify your httpd configuration:
#   ./install_module.sh update [httpd.conf]
echo "Hello, Docker!"
