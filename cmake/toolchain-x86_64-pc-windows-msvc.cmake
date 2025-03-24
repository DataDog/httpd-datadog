# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache 2.0 License. This product includes software developed at
# Datadog (https://www.datadoghq.com/).
#
# Copyright 2024-Present Datadog, Inc.

# the name of the target operating system
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_VERSION 10.0)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_RC_COMPILER ${TOOLCHAIN_ROOT}/llvm-rc)
set(CMAKE_LINKER ${TOOLCHAIN_ROOT}/lld-link)
set(CMAKE_RANLIB ${TOOLCHAIN_ROOT}/llvm-ranlib)
set(CMAKE_STRIP /usr/bin/strip)
set(CMAKE_AR ${TOOLCHAIN_ROOT}/llvm-lib)
set(CMAKE_NM ${TOOLCHAIN_ROOT}/llvm-nm)
set(CMAKE_MT ${TOOLCHAIN_ROOT}/llvm-mt)

set(triple x86_64-pc-windows-msvc)
set(cl_flags "-Qunused-arguments -DWIN32 -D_WINDOWS -imsvc ${XWIN_ROOT}/crt/include -imsvc ${XWIN_ROOT}/sdk/include/ucrt -imsvc ${XWIN_ROOT}/sdk/include/shared -imsvc ${XWIN_ROOT}/sdk/include/um")
set(lk_flags "-libpath:${XWIN_ROOT}/crt/lib/x86_64 -libpath:${XWIN_ROOT}/sdk/lib/ucrt/x86_64 -libpath:${XWIN_ROOT}/sdk/lib/um/x86_64")

set(CMAKE_C_COMPILER   ${TOOLCHAIN_ROOT}/clang-cl)
set(CMAKE_C_COMPILER_TARGET ${triple})
set(CMAKE_C_FLAGS_INIT ${cl_flags})
set(CMAKE_C_STANDARD_LIBRARIES "")
set(CMAKE_C_COMPILER_FRONTENT_VARIANT "MSVC")

set(CMAKE_CXX_COMPILER ${TOOLCHAIN_ROOT}/clang-cl)
set(CMAKE_CXX_COMPILER_TARGET ${triple})
set(CMAKE_CXX_FLAGS_INIT ${cl_flags})
set(CMAKE_CXX_STANDARD_LIBRARIES "")
set(CMAKE_CXX_COMPILER_FRONTENT_VARIANT "MSVC")

set(CMAKE_EXE_LINKER_FLAGS_INIT ${lk_flags})
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${lk_flags}")
set(CMAKE_STATIC_LINKER_FLAGS_INIT "${lk_flags}")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "${lk_flags}")

