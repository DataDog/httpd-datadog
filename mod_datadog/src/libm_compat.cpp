// The module is built against musl, where libm is part of libc, and its libc
// dependency is removed (patch_away_libc): the host process provides libc. On
// glibc hosts, Apache doesn't load libm, so libm functions used by dependencies
// must be defined here, like ceil/ceilf in
// deps/nginx-datadog/build_env/glibc_compat.c.

#if defined(__linux__) && !defined(__GLIBC__)

// used by dd-trace-cpp (OpenTelemetry tracestate sampling)
extern "C" double round(double x) {
  double result;
#if defined(__x86_64__)
  // truncate, then round half away from zero. x - result is exact: same sign
  // and |result| <= |x|.
  // NOLINTNEXTLINE(hicpp-no-assembler)
  __asm__("roundsd $0x0B, %[x], %[result]"
          : [result] "=x"(result)
          : [x] "x"(x));
  const double fraction = x - result;
  if (fraction >= 0.5) {
    result += 1.0;
  } else if (fraction <= -0.5) {
    result -= 1.0;
  }
#elif defined(__aarch64__)
  // round to nearest, ties away from zero
  // NOLINTNEXTLINE(hicpp-no-assembler)
  __asm__("frinta %d0, %d1\n" : "=w"(result) : "w"(x));
#else
#error "round is not implemented for this architecture"
#endif
  return result;
}

#endif
