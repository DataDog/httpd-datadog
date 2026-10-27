Include(FetchContent)

FetchContent_Declare(
  Catch2
  GIT_REPOSITORY https://github.com/catchorg/Catch2.git
  GIT_TAG        v2.13.9
)

FetchContent_MakeAvailable(Catch2)

add_executable(tests main.cpp test_utils.cpp ../rum/unit-test/test_rum_content_type.cpp)

target_include_directories(tests PRIVATE ${CMAKE_SOURCE_DIR}/mod_datadog/src)

# httpd and fmt are only needed for the headers of utils.h.
target_link_libraries(tests PRIVATE Catch2::Catch2 httpd fmt)

# These tests link the host APR, and run at build time to list test cases.
if(HTTPD_DATADOG_ENABLE_RUM AND
   CMAKE_SYSTEM_PROCESSOR STREQUAL CMAKE_HOST_SYSTEM_PROCESSOR)
  find_library(STREAM_APR_LIBRARY NAMES apr-1
    HINTS "${HTTPD_SRC_DIR}/httpd-build/lib")
  find_library(STREAM_APRUTIL_LIBRARY NAMES aprutil-1
    HINTS "${HTTPD_SRC_DIR}/httpd-build/lib")
  if(NOT STREAM_APR_LIBRARY OR NOT STREAM_APRUTIL_LIBRARY)
    message(WARNING "Native APR not found: skip RUM streaming tests")
  else()
    add_executable(rum_streaming_tests main.cpp
      ../rum/unit-test/test_rum_streaming.cpp
      ../../mod_datadog/src/rum/filter.cpp
      ../../mod_datadog/src/rum/telemetry.cpp)
    target_include_directories(rum_streaming_tests PRIVATE
      ${CMAKE_SOURCE_DIR}/mod_datadog/src)
    target_compile_definitions(rum_streaming_tests PRIVATE HTTPD_DD_RUM)
    target_link_libraries(rum_streaming_tests PRIVATE
      Catch2::Catch2 httpd dd-trace-cpp-static inject_browser_sdk_ffi fmt
      ${STREAM_APR_LIBRARY} ${STREAM_APRUTIL_LIBRARY})

    include(CheckCXXSourceCompiles)
    set(CMAKE_REQUIRED_FLAGS -fsanitize=address)
    set(CMAKE_REQUIRED_LINK_OPTIONS -fsanitize=address)
    check_cxx_source_compiles("int main() { return 0; }" HTTPD_DATADOG_HAS_ASAN)
    unset(CMAKE_REQUIRED_FLAGS)
    unset(CMAKE_REQUIRED_LINK_OPTIONS)
    if(HTTPD_DATADOG_HAS_ASAN)
      target_compile_options(rum_streaming_tests PRIVATE
        -fsanitize=address -fno-omit-frame-pointer)
      target_link_options(rum_streaming_tests PRIVATE -fsanitize=address)
    else()
      message(STATUS "RUM streaming tests run without AddressSanitizer")
    endif()

    # One CTest test per test case, so a hang only fails its own case.
    list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/contrib)
    include(Catch)
    catch_discover_tests(rum_streaming_tests
      TEST_PREFIX "rum-streaming/" PROPERTIES TIMEOUT 10)
  endif()
endif()
