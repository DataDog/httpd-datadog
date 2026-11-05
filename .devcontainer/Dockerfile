# Build image for httpd-datadog GitLab CI.
#
# It contains:
#   - musl toolchain whose binaries also run on glibc (musl-build-env, see
#     https://github.com/DataDog/musl-toolchain-glibc-support)
#   - httpd 2.4 source code
#   - Tools necessary to build httpd and mod_datadog
#   - Rust toolchain for RUM (inject-browser-sdk requires Rust 1.91+)
#   - uv (fast Python package manager for tests)

FROM registry.datadoghq.com/musl-build-env:1.0.6@sha256:fd1ab35b2a51538623740c499606a0f6240947b509b39bd1c754d7a5ee4b8c6b

# Install Ninja build tool and clang-tidy
RUN apk add --no-cache clang-extra-tools samurai

# Install dependencies for httpd
RUN apk add --no-cache autoconf expat expat-dev gpg gpg-agent libtool pcre-dev pcre2-dev py-pip zip

# Install dependencies for code coverage upload
RUN apk add --no-cache curl jq

# Install Rust toolchain
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -yq --default-toolchain 1.91.0 \
  && ln -s ~/.cargo/bin/cargo /usr/bin/cargo

RUN cargo install --locked cbindgen --version 0.26.0 \
  && ln -s ~/.cargo/bin/cbindgen /usr/local/bin/cbindgen

# Install uv (Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv

# Setup httpd 2.4 source
COPY scripts/setup-httpd.py setup-httpd.py
RUN python3 ./setup-httpd.py -o httpd 2.4.58 \
 && cd httpd \
 && CC=clang ./configure --with-included-apr --prefix=$(pwd)/httpd-build --enable-mpms-shared="all" \
 && make -j \
 && make -j install

# Share C, C++, and Rust compilation results between ephemeral CI runners.
RUN apk add --no-cache sccache

LABEL org.opencontainers.image.source="https://github.com/DataDog/httpd-datadog"
