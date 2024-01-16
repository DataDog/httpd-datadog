# Dev documentation

## Fork, Clone, Branch and Create your PR
Contributions are welcome!

### Rules
- ** Follow the pattern of what you already see in the code. **
- Follow the coding style.

# Development

## Prerequisites

| Tool | Version |
| ---- | ------- |
| `clang` | x.0.0 |
| `python` | 3.x |
| `cmake` | 3.x |
| `docker` | | For testing purpose |

Once you got a valid `python` installation, install all the dependencies with

````sh
pip install -r requirement.txt
````

Finally, you need HTTPD source code available. Use [scripts/setup-httpd.py](./scripts/setup-httpd.py) script:

````sh
python scripts/setup-httpd.py

usage: Download HTTPD and dependencies source code [-h] [-o OUTPUT] version

positional arguments:
  version               HTTPD version to download

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Directory where HTTPD will be extracted
````

### Compiling
CMake is our "build system". If you are not familiar with CMake, read [the tutorial.](https://cmake.org/cmake/help/latest/guide/tutorial/index.html)

Configure and compile all targets in release:

````sh
cmake -B build -DCMAKE_BUILD_TYPE=Release -DHTTPD_SRC_DIR=httpd-2.4 .
cmake --build build -j
````

### Testing
For nowm there are only integration tests. `docker-compose` orchestrate a runtime environment and the test suite interact with
It should be as simple as:

````sh
python test/integration-test
````
## Repository

## Contribution guideline
What tis not accepted. Adding specific tags -> use `DD_HEADER_TAGS`

## How to debug

## Test
