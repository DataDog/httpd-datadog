# Contributing to the Datadog Apache Httpd Module

## Conventions

Follow [docs/conventions.md](doc/conventions.md).

## Format

C++ is formatted with `clang-format-14` and `.clang-format`.

```sh
./scripts/codestyle.sh lint     # check; fails on drift
./scripts/codestyle.sh format   # rewrite files
```

## Static Analysis

C++ is analyzed with **clang-tidy-17** (pinned to the LLVM 17 toolchain in the
devcontainer) using the shared `.clang-tidy` baseline. Warnings are errors.

Do not run clang-tidy on the host. Tidy must use the same compiler, flags, and
sysroot as the real build (`ci-dev`). Locally:

```sh
make lint-tidy
```

That builds/pulls the devcontainer, configures CMake inside it (`ci-dev`, RUM
off, `HTTPD_DATADOG_ENABLE_CLANG_TIDY`), and builds `mod_datadog` so CMake
invokes clang-tidy-17 with the exact compile line. `rum/`, `deps/`, and tests
are not on that target. `./scripts/clang-tidy.sh` re-execs through
`make lint-tidy` when run on the host. CI runs the same script in
`ghcr.io/datadog/httpd-datadog/devcontainer:main`.

## Clone

When cloning the repo, initialize the submodules you need. For a standard build:

```sh
git submodule update --init deps/dd-trace-cpp deps/nginx-datadog
```

The `deps/inject-browser-sdk` submodule is a private repository and is only required for RUM builds
(with `-DHTTPD_DATADOG_ENABLE_RUM=ON`). If you have access, use `--recursive` instead to pull it as
well:

```sh
git submodule update --init --recursive
```

## Prerequisites

| Tool | Version |
| ---- | ------- |
| `clang` | 17+ |
| `cmake` | 3.12+ |
| `gcc` | 13.2+ |
| `python` | 3.11+ |

Once you got a valid Python installation, install all the dependencies with:

```sh
pip install -r requirements.txt
```

## Install Rust

The RUM variant requires Rust to build:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Relaunch your terminal (or do `source ~/.cargo/env`).

## Compiling

### Setup `httpd`

In order to build the module you have to configure `httpd` with the
[scripts/setup-httpd.py](./scripts/setup-httpd.py) script. Check what is the latest available
version on [Apache website](https://httpd.apache.org), then:

```sh
export HTTPD_VERSION=2.4.66
python scripts/setup-httpd.py $HTTPD_VERSION
cd httpd
./configure --with-included-apr --prefix=$(pwd)/httpd-build --enable-mpms-shared="all"
```

### Build the Module

CMake is our build system.

Configure and compile all targets in release:

```sh
cmake -B build -DCMAKE_BUILD_TYPE=Release -DHTTPD_SRC_DIR=httpd .
cmake --build build -j
```

### Testing

For now there are only [integration tests](./test/integration-test/).

### Build Devcontainer Image

```bash
make ci-build          # Non-RUM CI build
make test-integration  # RUM-enabled build and integration tests
make dev-shell         # Interactive devcontainer shell
```

The devcontainer image is selected for the host architecture and includes the
LLVM toolchain, httpd source, Rust, and uv.

### Running Specific Tests Inside Docker

```bash
make dev-shell
# Inside container:
.devcontainer/run-integration-tests.sh \
  scenarios/test_rum.py::test_rum_selective_disabling -m requires_rum
```

### Key Paths Inside the CI Image

- `/httpd` — httpd source
- `/httpd/httpd-build/bin/apachectl` — pre-built apachectl binary
- `/sysroot/{arch}-none-linux-musl/Toolchain.cmake` — cross-compilation toolchain

### Test Markers

- `requires_rum` — tests needing RUM-enabled build (`-DHTTPD_DATADOG_ENABLE_RUM=ON`)
- Tests without markers run against the standard build

## CI

GitLab CI status can be checked via `glab ci` on the [automated
mirror](https://gitlab.ddbuild.io/DataDog/httpd-datadog).
