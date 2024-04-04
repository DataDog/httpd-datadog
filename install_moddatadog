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
#
## TODO: check `mod_so` is available with httpd -l | grep mod_so
## TODO: check `mod_ddtrace` is available too
usage() {
  cat<<'END_USAGE'
  TODO
END_USAGE
}

REPO="https://github.com/DataDog/httpd-datadog"

is_installed() {
  command -v "$1" > /dev/null 2>&1
}

get_latest_release() {
  curl --silent "https://api.github.com/repos/httpd-datadog/releases/latest" | jq --raw-output .tag_name
}

update_conf() {
  # TODO: if ddtrace_module already there then update the location instead
  so_location="$1"
  httpd_conf="$2"
  sed -i \
      -e 's/^#\(LoadModule ddtrace_module \${so_location}\)/\1/' \
      ${httpd_conf}
}

download() {
  platform="$1"
  arch="$2"
  httpd_version=$3
  output_dir=$4
  release_tag=$(get_latest_release)

  pubkey="pubkey.pgp"
  tarball="mod_ddtrace-${httpd_version}-${platform}-${arch}.tar.gz"
  tarball_sign="mod_ddtrace-${httpd_version}-${platform}-${arch}.tar.gz.asc"

  wget "${REPO}/releases/download/${release_tag}/${tarball}"

  if [ "$VERIF" == "true" ]; then
    wget "${REPO}/releases/download/${release_tag}/${tarball_sign}"
    wget "${REPO}/releases/download/${release_tag}/${pubkey}"
    gpg --import ${pubkey}
    gpg --verify ${tarball} ${tarball_sign}
  fi

  tar -xzvf "${tarball}" -C "${output_dir}"
  rm "${tarball}"
}

# TODO: find httpd binary if not provided
# TODO: find httpd version
# TODO: support --version to install a specific version
subcommand=""

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    download)
      subcommand="download"
      shift
      ;;
    update)
      subcommand="update"
      shift
      ;;
  esac

  shift $(( $# > 0 ? 1 : 0 ))
done

if ! is_installed wget; then
  >&2 "Missing wget."
  exit 1
fi

if ! is_installed pgp; then
  >&2 "Missing pgp. If you do not need to check the validity of the binary use `--no-verify`"
  exit 1
fi

if [ "$subcommand" == "download" ]; then
  echo "download"
fi

# Do you want to continue? [y/N]
# sh -s -- --yes

#           httpd location : httpd
#            httpd version : 2.4.58
# httpd configuration file : /apache/k....
#      mod_ddtrace version : 0.1.0
#   installation directory : /tmp/datadog 
