# Datadog Apache HTTPD Tracing Module

This module adds distributed tracing to [Apache HTTP Server](https://httpd.apache.org/). Leveraging [Datadog's tracing library](https://github.com/DataDog/dd-trace-cpp/), it provides access to Datadog-specific functionality.

## Getting started

### Compatibility Requirements
Only [Apache HTTP Server 2.4.x](https://httpd.apache.org) is supported.

For a detail understanding of our release cycle and `httpd` support, read our [Release documentation.](./doc/release.md)

### Install script

````sh
curl -sL https://github.com/DataDog/httpd-datadog/tree/main/scripts/install.sh | sh
````

### Manual

Download a gzippeed tarball from a recent release, extract it to wherever `httpd` looks for modules and add the following line to the top of your configuration file:
````sh
LoadModule ddtrace_module <MODULE_PATH>/mod_ddtrace.so
````

Then run `httd -t` to test the new configuration. You can find the ddtrace log.

````sh
cat <LOG> | grep ddtrace
````

## Configuration
Once the module is loaded, by default all request are traced and sent to the Datadog Agent.
It is possible to change the module default behavior, to know more how check our [Configuration page.](./docs/configuration) 

## Contributing

We welcome contribution, before doing so, please read our [developer documentation](./docs/dev.md).

## Licence

TBD
