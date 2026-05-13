# Build image for httpd-datadog GitLab CI.
# [verify-nydus-merge-platform] Hash-perturbing comment so CI rebuilds
# the image (skip-if-exists in devcontainer.yml would otherwise reuse
# the existing nydus-only manifest at the original hash).
#
# It contains:
#   - LLVM 17 toolchain with musl sysroot for cross-compilation
#   - httpd 2.4 source code
#   - Tools necessary to build httpd and mod_datadog
#   - Rust toolchain for RUM (inject-browser-sdk requires Rust 1.73+)
#   - uv (fast Python package manager for tests)
#
# Toolchain files are sourced from deps/nginx-datadog/build_env/.
#
# Arch is auto-derived from `uname -m` inside each RUN (matches the
# buildx --platform the container runs on), so callers don't have to
# pass --build-arg ARCH=. The VSCode "Reopen in Container" flow can't
# auto-detect host arch from devcontainer.json, so relying on uname
# keeps it correct without env-var gymnastics. `ARG ARCH` stays declared
# (as an override) so external callers that already pass it — e.g. the
# dd-repo-tools template's auto-detected build-arg — don't trigger
# "ARG not declared" warnings.
FROM alpine:3.20.3 AS sysroot

ARG LLVM_VERSION=17.0.6
ARG ARCH

COPY deps/nginx-datadog/build_env/CHECKSUMS /CHECKSUMS

RUN apk --no-cache add alpine-sdk coreutils sudo bash samurai python3 linux-headers \
	compiler-rt clang llvm lld wget cmake make binutils musl-dev git patchelf xz lit
RUN wget https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VERSION}/llvm-project-${LLVM_VERSION}.src.tar.xz && \
    grep -F llvm-project-${LLVM_VERSION}.src.tar.xz /CHECKSUMS | sha512sum --check && \
    tar -xvf llvm-project-${LLVM_VERSION}.src.tar.xz

COPY deps/nginx-datadog/build_env/locale.h.diff /locale.h.diff
RUN cd /usr/include && patch -p0 < /locale.h.diff

COPY deps/nginx-datadog/build_env/alltypes.h.diff /alltypes.h.diff
RUN cd /usr/include && patch -p0 < /alltypes.h.diff

RUN cd llvm-project-${LLVM_VERSION}.src && mkdir -p build && cd build && \
    cmake -G Ninja \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_C_FLAGS="-fno-omit-frame-pointer -D_LIBCPP_HAS_NO_C11_ALIGNED_ALLOC=1" \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_CXX_FLAGS="-fno-omit-frame-pointer -D_LIBCPP_HAS_NO_C11_ALIGNED_ALLOC=1" \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DLIBUNWIND_ENABLE_SHARED=OFF \
    -DLIBUNWIND_ENABLE_STATIC=ON \
    -DLIBUNWIND_USE_COMPILER_RT=ON \
    -DLIBCXXABI_ENABLE_SHARED=OFF \
    -DLIBCXXABI_USE_LLVM_UNWINDER=ON \
    -DLIBCXXABI_ENABLE_STATIC_UNWINDER=ON \
    -DLIBCXXABI_USE_COMPILER_RT=ON \
    -DLIBCXX_ENABLE_SHARED=OFF \
    -DLIBCXX_HAS_MUSL_LIBC=ON \
    -DLIBCXX_USE_COMPILER_RT=ON \
    -DLIBCXX_ENABLE_STATIC_ABI_LIBRARY=ON \
    -DLLVM_ENABLE_RUNTIMES="libcxx;libcxxabi;libunwind" \
    -DLLVM_EXTERNAL_LIT=/usr/bin/lit ../runtimes && \
    ninja -v install-unwind install-cxxabi install-cxx

RUN cd /usr/lib && ln -s gcc/*/*/ resource_dir
RUN cd /usr/lib && ln -s clang/${LLVM_VERSION%%.*}/lib/linux/libclang_rt.builtins-*.a libclang_rt.builtins.a

RUN rm -rf /llvm-project-${LLVM_VERSION}.src
RUN rm -f llvm-project-${LLVM_VERSION}.src.tar.xz

RUN arch=${ARCH:-$(uname -m)} && \
    mkdir -p /sysroot/${arch}-none-linux-musl/usr && \
    ln -s /usr/lib /sysroot/${arch}-none-linux-musl/usr/ && \
    ln -s /usr/include /sysroot/${arch}-none-linux-musl/usr/ && \
    ln -s /lib /sysroot/${arch}-none-linux-musl/ && \
    ln -s /usr/lib/llvm${LLVM_VERSION%%.*}/lib/clang/${LLVM_VERSION%%.*}/lib /sysroot/${arch}-none-linux-musl/usr/lib/resource_dir/lib

# Both Toolchain.cmake variants are staged; the RUN below picks the one
# matching the build platform. (COPY can't use a shell-derived path, so
# we copy both and select at RUN-time instead.)
COPY deps/nginx-datadog/build_env/Toolchain.cmake.x86_64 /tmp/Toolchain.cmake.x86_64
COPY deps/nginx-datadog/build_env/Toolchain.cmake.aarch64 /tmp/Toolchain.cmake.aarch64
RUN arch=${ARCH:-$(uname -m)} && \
    cp /tmp/Toolchain.cmake.${arch} /sysroot/${arch}-none-linux-musl/Toolchain.cmake && \
    rm /tmp/Toolchain.cmake.x86_64 /tmp/Toolchain.cmake.aarch64

# see https://github.com/llvm/llvm-project/issues/60572
RUN arch=${ARCH:-$(uname -m)} && \
    mv /usr/lib/gcc/${arch}-alpine-linux-musl/13.2.1/include/stdatomic.h /usr/lib/gcc/${arch}-alpine-linux-musl/13.2.1/include/stdatomic.h_ && \
    cp /usr/lib/llvm${LLVM_VERSION%%.*}/lib/clang/${LLVM_VERSION%%.*}/include/stdatomic.h /usr/lib/gcc/${arch}-alpine-linux-musl/13.2.1/include/stdatomic.h

COPY deps/nginx-datadog/build_env/glibc_compat.c /sysroot/
RUN arch=${ARCH:-$(uname -m)} && \
    clang --sysroot /sysroot/${arch}-none-linux-musl/ -fpie -O2 -fno-omit-frame-pointer \
        -ggdb3 -c /sysroot/glibc_compat.c -o /tmp/glibc_compat.o && \
    ar rcs /sysroot/${arch}-none-linux-musl/usr/lib/libglibc_compat.a /tmp/glibc_compat.o && \
    rm /tmp/glibc_compat.o

# Install dependencies for httpd
RUN apk add --no-cache autoconf expat expat-dev gpg gpg-agent libtool pcre-dev pcre2-dev py-pip zip

# Install dependencies for code coverage upload
RUN apk add --no-cache nodejs npm

# Install Rust toolchain
RUN apk add --no-cache curl
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -yq --default-toolchain 1.73.0 \
  && ln -s ~/.cargo/bin/cargo /usr/bin/cargo

RUN cargo install --locked cbindgen --version 0.26.0 \
  && ln -s ~/.cargo/bin/cbindgen /usr/local/bin/cbindgen

# Install uv (Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv

# Setup httpd 2.4 source
COPY scripts/setup-httpd.py setup-httpd.py
RUN python3 ./setup-httpd.py -o httpd 2.4.58 \
 && cd httpd \
 && ./configure --with-included-apr --prefix=$(pwd)/httpd-build --enable-mpms-shared="all" \
 && make -j \
 && make -j install
