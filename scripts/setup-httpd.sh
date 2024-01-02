#!/bin/sh
set -e
# Download HTTPD source code and its dependencies

usage() {
  cat << "END_USAGE"
setup-httpd - Download httpd source code and its dependencies

usage:
  ./setup-httpd.sh [-o|--output-dir]

options:
  -h, --help        Show this help message and exit
  -o, --output-dir  Set httpd source code location
END_USAGE
}

installed() {
  command -v "$1" > /dev/null 2>&1
}

OUTPUT_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [ -z "$OUTPUT_DIR" ]; then
  OUTPUT_DIR="httpd"
fi

if ! installed git; then
  >&2 "Missing git"
  exit 1
fi

git clone --branch 2.4.58 --depth 1 https://github.com/apache/httpd.git ${OUTPUT_DIR}
git clone --branch 1.6.3 --depth 1 https://github.com/apache/apr-util.git ${OUTPUT_DIR}/srclib/apr-util
git clone --branch 1.7.4  --depth 1 https://github.com/apache/apr.git ${OUTPUT_DIR}/srclib/apr

cd httpd
./buildconf
