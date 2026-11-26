#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir=${HTTPD_DATADOG_SOURCE:-$root}
sdk=${HTTPD_SRC_DIR:?Set HTTPD_SRC_DIR to the extracted native AIX Apache SDK}
toolchain_root=${AIX_TOOLCHAIN_ROOT:?Set AIX_TOOLCHAIN_ROOT to the extracted toolchain}
cxx_root=${AIX_CXX_ROOT:?Set AIX_CXX_ROOT to the threaded AIX 7.2 runtime}
build_dir=${HTTPD_AIX_BUILD_DIR:-$root/build-aix}
cxx_platform="$cxx_root/include/powerpc-ibm-aix7.2.0.0"
cxx_flags="-maix64 -mcpu=powerpc64 -pthread -D_ALL_SOURCE -nostdinc++"
cxx_flags+=" -isystem $cxx_root/include -isystem $cxx_platform/pthread/ppc64 -isystem $cxx_platform"
python3 "$root/scripts/prepare-aix-imports.py" "$sdk" "$toolchain_root" "${AIX_TRIPLE:-powerpc-ibm-aix7.3.0.0}"
cache_args=()
if [[ -n ${AIX_FEATURE_CACHE:-} ]]; then
  cache_args=(-C "$AIX_FEATURE_CACHE")
fi
cmake "${cache_args[@]}" -S "$source_dir" -B "$build_dir" \
  -DCMAKE_TOOLCHAIN_FILE="$root/cmake/toolchains/aix.cmake" \
  -DAIX_TOOLCHAIN_ROOT="$toolchain_root" -DAIX_CXX_ROOT="$cxx_root" \
  -DAIX_TRIPLE="${AIX_TRIPLE:-powerpc-ibm-aix7.3.0.0}" \
  -DCMAKE_C_FLAGS="-maix64 -mcpu=powerpc64 -pthread -D_ALL_SOURCE" \
  -DCMAKE_CXX_FLAGS="$cxx_flags" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$cxx_root/lib" \
  -DCMAKE_SHARED_LINKER_FLAGS="-L$cxx_root/lib" \
  -DHTTPD_SRC_DIR="$sdk" -DHTTPD_DATADOG_ENABLE_RUM=OFF \
  -DBUILD_TESTING=OFF -DDD_TRACE_BUILD_TESTING=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel "${BUILD_JOBS:-6}" --target mod_datadog
if [[ -f "$sdk/bin/httpd_64" ]]; then
  python3 "$root/test/aix/check_module.py" "$build_dir/mod_datadog/mod_datadog.so" "$sdk"
fi
