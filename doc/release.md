## Versioning
This module adheres to the principles of [Semantic Versioning (SemVer)](https://semver.org/). The version number is expressed as MAJOR.MINOR.PATCH, with the following guidelines:

- MAJOR version: Increment for incompatible API changes.
- MINOR version: Increment for backward-compatible feature additions.
- PATCH version: Increment for backward-compatible bug fixes.

We release at least one version by quarter. Nonetheless, we allow ourselves to release more if necessary.

## Compatibility Requirements

Since this module is extending [Apache HTTP Server]() capabilities using the C interface, each version are tied to a specific version the webserver.
Each module version will receive support for the specified HTTPD version range until the respective HTTPD versions reach their end-of-life.

The following table outlines the compatibility between module versions and HTTPD versions:

| `mod_ddtrace` version | HTTPD Version Range | Status  |
| --------------------- | ------------------- | ------- |
| 1.0                   | 2.4.0 - 2.4.54      | Current |

