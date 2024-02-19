# Datadog Apache HTTPD Tracing Module

This module adds distributed tracing to [Apache HTTP Server](https://httpd.apache.org/). Leveraging [Datadog's tracing library](https://github.com/DataDog/dd-trace-cpp/), it provides access to Datadog-specific functionality.

## Getting started

### Compatibility Requirements
Only [Apache HTTP Server 2.4.x](https://httpd.apache.org) is supported.

For a detail understanding of our release cycle and Apache HTTPD support, read our [Release documentation.](./doc/release.md)

### Automatic installation

````sh
# 1. Download install_moddatadog
curl -LO https://github.com/DataDog/httpd-datadog/scripts/install_moddatadog

# (Optional) Validate the binary
curl -LO https://github.com/DataDog/httpd-datadogn/install_moddatadog.sha256
echo "$(cat install_moddatadog.sha256) install_moddatadog" | sha256sum --check

# 2. Execute install_moddatadog
./install_moddatadog
````

This script do:

1. TBD

### Manual installation

Download a gzipped tarball compatible with your version of Apache HTTPD, extract it to wherever `httpd` looks for modules and add the following line to the top of your configuration file:
````sh
LoadModule datadog_module <MODULE_PATH>/mod_ddtrace.so
````

Then run `httpd -t <CONFIG_FILE>` to test the new configuration.

## Configuration
Once the module is loaded, by default all requests are traced and sent to the Datadog Agent.
To change the module default behaviour, check our [Configuration page.](./doc/configuration.md) 

## Development / Contribution

We welcome contribution, before doing so, please read our [CONTRIBUTING.md](./CONTRIBUTING.md).

## Licence

TBD
