# Contributing

## Fork, Clone, Branch and Create your PR

When cloning the repo, you have to initialize the submodules:
```sh
git submodule update --init --recursive
```

### Rules
- Follow the pattern of what you already see in the code.
- Follow the coding style.

# Development

## Prerequisites

| Tool | Version | Notes |
| ---- | ------- | ----- |
| `clang` or `gcc` | 14+ or 11.4+ | |
| `python` | 3.0+ | |
| `cmake` | 3.12+ | |

Once you got a valid `python` installation, install all the dependencies with

````shell
pip install -r requirements.txt
````

## Compiling

### Setup `httpd`

In order to build the module you have to configure `httpd` with the [scripts/setup-httpd.py](./scripts/setup-httpd.py) script:

```sh
python scripts/setup-httpd.py -o httpd $HTTPD_VERSION
cd httpd
./configure --with-included-apr --prefix=$(pwd)/httpd-build --enable-mpms-shared="all"
```

### Build the Module

CMake is our build system. If you are not familiar with CMake, read [the tutorial.](https://cmake.org/cmake/help/latest/guide/tutorial/index.html)

Configure and compile all targets in release:

```sh
cmake -B build -DCMAKE_BUILD_TYPE=Release -DHTTPD_SRC_DIR=httpd .
cmake --build build -j
```

### Testing

For now there are only [integration tests](./test/integration-test/).

## How to Debug

Run with `-X`.
