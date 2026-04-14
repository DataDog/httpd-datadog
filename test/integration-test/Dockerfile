# Dockerfile for running httpd-datadog integration tests
FROM alpine:3.21

RUN apk add --no-cache \
    autoconf \
    build-base \
    cmake \
    curl \
    expat-dev \
    git \
    libtool \
    libunwind-dev \
    linux-headers \
    pcre2-dev \
    python3

# uv (Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv

# Rust toolchain (required to build the RUM module)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -yq --default-toolchain 1.73.0 \
    && ln -s ~/.cargo/bin/cargo /usr/bin/cargo
RUN cargo install --locked cbindgen --version 0.26.0 \
    && ln -s ~/.cargo/bin/cbindgen /usr/local/bin/cbindgen

# Apache httpd 2.4
COPY scripts/setup-httpd.py /tmp/setup-httpd.py
RUN python3 /tmp/setup-httpd.py -o /httpd 2.4.66 \
    && cd /httpd \
    && ./configure \
        --with-included-apr \
        --prefix=/httpd/httpd-build \
        --enable-mpms-shared="all" \
    && make -j$(nproc) \
    && make install

# Copy project source
WORKDIR /workspace
COPY . .

# inject-browser-sdk is a private GitHub repository and cannot be cloned during
# docker build. Copy the pre-fetched source from the local cmake build directory
# and tell cmake to use it directly, bypassing the git clone.
# Hence the following have been run locally at least once:
# cmake --build build-rum
COPY build-rum/_deps/injectbrowsersdk-src /inject-browser-sdk-src

# Build without RUM support
RUN cmake -B build -DHTTPD_SRC_DIR=/httpd . \
    && cmake --build build -j$(nproc)

# Build with RUM support
RUN cmake -B build-rum \
    -DHTTPD_SRC_DIR=/httpd \
    -DHTTPD_DATADOG_ENABLE_RUM=ON \
    -DFETCHCONTENT_SOURCE_DIR_INJECTBROWSERSDK=/inject-browser-sdk-src \
    . \
    && cmake --build build-rum -j$(nproc)

# Python test dependencies
WORKDIR /workspace/test/integration-test
RUN uv sync

# Run all integration tests by default.
# The test suite auto-selects the correct module variant (RUM / non-RUM) per test.
CMD ["uv", "run", "pytest", "--bin-path=/httpd/httpd-build/bin/apachectl", "-v"]
