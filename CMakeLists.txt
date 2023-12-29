# TODO
# - versioning 
# - toolchain (msvc, llvm, gcc)
cmake_minimum_required(VERSION 3.12)

project(httpd-datadog)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON) # does not produce the json file
# set(CMAKE_EXPORT_COMPILE_COMMANDS ON CACHE INTERNAL "") # works

if (NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE ReleaseWithDeb)
endif ()

if(NOT HTTPD_BUILD_DIR)
  message(FATAL_ERROR "Missing nginx source directory. Use -DHTTPD_BUILD_DIR")
endif()

add_library(httpd INTERFACE)
target_include_directories(
  httpd
  INTERFACE
  ${HTTPD_BUILD_DIR}/include
)

# target_include_directories(
#   httpd
#   INTERFACE
#   ${HTTPD_DIR}/include
#   ${HTTPD_DIR}/os/unix #<--- add condition
#   ${HTTPD_DIR}/srclib/apr/include
#   ${HTTPD_DIR}/srclib/apr-util/include
# )

add_subdirectory(dd-trace-cpp EXCLUDE_FROM_ALL)
add_subdirectory(mod_ddtrace)
