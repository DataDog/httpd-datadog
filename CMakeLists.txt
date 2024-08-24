# TODO
# - versioning 
# - toolchain (msvc, llvm, gcc)
cmake_minimum_required(VERSION 3.12)

project(httpd-datadog)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(HTTPD_DATADOG_ENABLE_COVERAGE OFF)

if (NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE ReleaseWithDeb)
endif ()

if(NOT HTTPD_SRC_DIR)
  message(FATAL_ERROR "Missing httpd source directory. Use -DHTTPD_SRC_DIR")
endif()

include(cmake/utils.cmake)
include(cmake/deps/fmt.cmake)
include(cmake/deps/corrosion.cmake)

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
