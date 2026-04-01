# Pre-fetch FetchContent dependencies for offline builds.
#
# Usage:
#   cmake -P scripts/prefetch-deps.cmake
#   cmake -DVENDOR_DIR=/custom/path -P scripts/prefetch-deps.cmake
#
# After running, pass FETCHCONTENT_SOURCE_DIR_* to your build:
#   cmake -B build \
#     -DFETCHCONTENT_SOURCE_DIR_CORROSION=vendor/corrosion \
#     -DFETCHCONTENT_SOURCE_DIR_INJECTBROWSERSDK=vendor/inject-browser-sdk \
#     ...
#
# This is useful for Docker builds where the container may not have
# access to private repos or the network.

cmake_minimum_required(VERSION 3.14)
include(FetchContent)

if(NOT VENDOR_DIR)
  set(VENDOR_DIR "${CMAKE_CURRENT_LIST_DIR}/../.deps")
endif()

get_filename_component(VENDOR_DIR "${VENDOR_DIR}" ABSOLUTE)
message(STATUS "Vendor directory: ${VENDOR_DIR}")

# Corrosion (public)
if(NOT EXISTS "${VENDOR_DIR}/corrosion/CMakeLists.txt")
  message(STATUS "Fetching Corrosion v0.5...")
  FetchContent_Populate(
    Corrosion
    GIT_REPOSITORY https://github.com/corrosion-rs/corrosion.git
    GIT_TAG        v0.5
    SOURCE_DIR     "${VENDOR_DIR}/corrosion"
    BINARY_DIR     "${VENDOR_DIR}/_build/corrosion"
    SUBBUILD_DIR   "${VENDOR_DIR}/_subbuild/corrosion"
  )
else()
  message(STATUS "Corrosion already fetched, skipping")
endif()

# inject-browser-sdk (private — requires GitHub access)
if(NOT EXISTS "${VENDOR_DIR}/inject-browser-sdk/Cargo.toml")
  message(STATUS "Fetching inject-browser-sdk...")
  FetchContent_Populate(
    InjectBrowserSDK
    GIT_REPOSITORY https://github.com/DataDog/inject-browser-sdk.git
    GIT_TAG        d6f95968037ecfa28fc1b52ef1648a0efac727ba
    SOURCE_DIR     "${VENDOR_DIR}/inject-browser-sdk"
    BINARY_DIR     "${VENDOR_DIR}/_build/inject-browser-sdk"
    SUBBUILD_DIR   "${VENDOR_DIR}/_subbuild/inject-browser-sdk"
  )
else()
  message(STATUS "inject-browser-sdk already fetched, skipping")
endif()

# Clean up intermediate build artifacts
file(REMOVE_RECURSE "${VENDOR_DIR}/_build" "${VENDOR_DIR}/_subbuild")

message(STATUS "All dependencies fetched to ${VENDOR_DIR}")
message(STATUS "")
message(STATUS "Use with cmake:")
message(STATUS "  -DFETCHCONTENT_SOURCE_DIR_CORROSION=${VENDOR_DIR}/corrosion")
message(STATUS "  -DFETCHCONTENT_SOURCE_DIR_INJECTBROWSERSDK=${VENDOR_DIR}/inject-browser-sdk")
