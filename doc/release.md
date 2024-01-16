## Versioning
This module adheres to the principles of [Semantic Versioning (SemVer)](https://semver.org/). The version number is expressed as MAJOR.MINOR.PATCH, with the following guidelines:

MAJOR version: Increment for incompatible API changes.
MINOR version: Increment for backward-compatible feature additions.
PATCH version: Increment for backward-compatible bug fixes.

Our release cycle is by quarter.

## Compatibility Requirements

Since this module is extending [Apache HTTP Server]() using , it is tied to a specific version the webserver.
A strict policy of versionning is required.

Version will be supported until the end of life
Versions 

httpd version | os | cpu |

The following table outlines the compatibility between module versions and HTTPD versions:

| `mod_ddtrace` version | HTTPD Version Range |
| --------------------- | ------------------- |
| 1.0                   | 2.4.0 - 2.4.54      |


Each module version will receive support for the specified HTTPD version range until the respective HTTPD versions reach their end-of-life.

