#!/bin/sh

# Check that mod_datadog loads in the Apache of Debian, serves a request, and
# unloads without crashing.
#
# Usage: test/check-module-load.sh <path to mod_datadog.so>

set -eu

module_path=$(realpath "$1")
# Use a port other than 80 because other containers of the CI job may use it.
port=7777

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends apache2 curl >/dev/null
sed -i "s/80/$port/" /etc/apache2/ports.conf /etc/apache2/sites-enabled/000-default.conf
cat >/etc/apache2/conf-enabled/datadog.conf <<EOF
LoadModule datadog_module $module_path
DatadogTracing On
EOF

# The configuration test loads and unloads the module.
apache2ctl -t
apache2ctl -DFOREGROUND &
server_pid=$!
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 \
    --output /dev/null "http://localhost:$port/"
apache2ctl -k stop
wait "$server_pid" || { echo "Apache exited with status $?" >&2; exit 1; }
echo "mod_datadog loaded, served a request, and unloaded."
