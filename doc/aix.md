# Experimental AIX cross-build

This prototype builds the tracing module for 64-bit, big-endian AIX against
stock Apache 2.4.66. RUM is disabled. It has not been loaded or executed on
AIX 7.2, AIX 7.3, or IBM HTTP Server (IHS).

The prototype used GCC 13.4.0, an AIX 7.3 system sysroot, and IBM GCC 13.3.0
threaded ppc64 C++ headers and runtime libraries built for AIX 7.2. The
cross-toolchain's default C++ runtime lacked threading support.

Provide these external inputs:

- `AIX_TOOLCHAIN_ROOT`: a directory containing `compiler/bin/` and
  `sysroot/usr/include/`, with a licensed AIX sysroot.
- `AIX_CXX_ROOT`: the threaded runtime under `lib/`, and matching headers
  under `include/`. The target headers are under
  `include/powerpc-ibm-aix7.2.0.0/pthread/ppc64/`.
- `HTTPD_SRC_DIR`: a writable SDK tree containing `include/`,
  `srclib/apr/include/`, `srclib/apr-util/include/`, `httpd.exp`, and
  `lib/libapr-1.so.0` plus `lib/libaprutil-1.so.0`. The prototype used IBM's
  AIX 7.1 Apache 2.4.66, APR 1.7.4, and APR-util 1.6.3 packages.

```sh
export AIX_TOOLCHAIN_ROOT=/path/to/aix-cross
export AIX_CXX_ROOT=/path/to/threaded-aix72-cxx
export HTTPD_SRC_DIR=/path/to/apache-aix-sdk
bash scripts/build-aix.sh
```

The result is `build-aix/mod_datadog/mod_datadog.so`. The script generates
APR import lists from the SDK's actual exports. The module uses the native
Apache export file and retains APR and APR-util as host dependencies.
Its default loader path includes `/opt/datadog-httpd/lib` and
`/opt/freeware/lib64`; set `LIBPATH` appropriately for a test installation.

The build verified XCOFF64 output and matched 7 Apache, 6 APR, and 1 APR-util
imports against those SDK binaries. This does not establish IHS ABI
compatibility or AIX 7.2 runtime compatibility. IHS requires matching headers,
module magic, exports, and APR libraries. Rebuild with an AIX 7.2 baseline
and the actual IHS SDK, then test loading, requests, and trace propagation.
Do not reuse AIX 7.3 feature-check caches for an AIX 7.2 sysroot.

With `bin/httpd_64` in the SDK, the build script also runs the host-side
XCOFF loader check. It can be run separately without executing AIX code:

```sh
python3 test/aix/check_module.py build-aix/mod_datadog/mod_datadog.so "$HTTPD_SRC_DIR"
```
