# TODO
# - versioning
# - toolchain (msvc, llvm, gcc)
cmake_minimum_required(VERSION 3.12)

project(httpd-datadog VERSION 1.0.4)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(ZLIB_USE_STATIC_LIBS ON)

option(HTTPD_DATADOG_ENABLE_RUM "Enable RUM product" OFF)
option(HTTPD_DATADOG_ENABLE_COVERAGE "Enable code coverage instrumentation" OFF)
option(HTTPD_DATADOG_PATCH_AWAY_LIBC "Patch away libc dependency" OFF)

if (NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE ReleaseWithDeb)
endif ()

if (NOT HTTPD_SRC_DIR)
  message(FATAL_ERROR "Missing httpd source directory. Use -DHTTPD_SRC_DIR")
endif ()

include(cmake/utils.cmake)
include(cmake/deps/fmt.cmake)

if (HTTPD_DATADOG_ENABLE_RUM)
  include(FetchContent)

  # Corrosion builds the Rust FFI crate and generates the C/C++ header via cbindgen.
  FetchContent_Declare(
    Corrosion
    GIT_REPOSITORY https://github.com/corrosion-rs/corrosion.git
    GIT_TAG v0.5
  )
  FetchContent_MakeAvailable(Corrosion)

  set(INJECT_BROWSER_SDK_DIR "${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk" CACHE PATH
      "Path to inject-browser-sdk source")

  corrosion_import_crate(MANIFEST_PATH "${INJECT_BROWSER_SDK_DIR}/Cargo.toml"
                         CRATES inject-browser-sdk-ffi
                         CRATE_TYPES staticlib)

  corrosion_experimental_cbindgen(
    TARGET inject_browser_sdk_ffi
    HEADER_NAME injectbrowsersdk.h
    FLAGS --config "${CMAKE_SOURCE_DIR}/deps/cbindgen.toml"
  )

  include(cmake/deps/rapidjson.cmake)
endif ()

add_library(httpd INTERFACE)
target_include_directories(
  httpd
  INTERFACE
  ${HTTPD_SRC_DIR}/include
  ${HTTPD_SRC_DIR}/srclib/apr/include
  ${HTTPD_SRC_DIR}/srclib/apr-util/include
)

if (UNIX)
  target_include_directories(
    httpd
    INTERFACE
    ${HTTPD_SRC_DIR}/os/unix
  )
endif (UNIX)

add_subdirectory(deps)
add_subdirectory(mod_datadog)
add_subdirectory(test/unit-test)

# Integration tests
enable_testing()
add_test(
  NAME integration-tests
  COMMAND uv run pytest
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/test/integration-test
)
set_tests_properties(integration-tests PROPERTIES
  ENVIRONMENT "HTTPD_MODULE_PATH=${CMAKE_BINARY_DIR}/mod_datadog/mod_datadog.so"
)
