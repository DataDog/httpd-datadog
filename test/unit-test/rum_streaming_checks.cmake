find_library(STREAM_APR_LIBRARY NAMES apr-1)
find_library(STREAM_APRUTIL_LIBRARY NAMES aprutil-1)
if(HTTPD_DATADOG_ENABLE_RUM AND STREAM_APR_LIBRARY AND STREAM_APRUTIL_LIBRARY
    AND NOT CMAKE_CROSSCOMPILING)
  add_executable(rum_streaming_tests test_rum_streaming.cpp
    ../../mod_datadog/src/rum/filter.cpp
    ../../mod_datadog/src/rum/telemetry.cpp)
  target_include_directories(rum_streaming_tests PRIVATE
    ${CMAKE_SOURCE_DIR}/mod_datadog/src)
  target_compile_definitions(rum_streaming_tests PRIVATE HTTPD_DD_RUM)
  target_compile_options(rum_streaming_tests PRIVATE
    -UNDEBUG -fsanitize=address -fno-omit-frame-pointer)
  target_link_options(rum_streaming_tests PRIVATE -fsanitize=address)
  target_link_libraries(rum_streaming_tests PRIVATE
    httpd dd-trace-cpp-static inject_browser_sdk_ffi fmt
    ${STREAM_APR_LIBRARY} ${STREAM_APRUTIL_LIBRARY})
  foreach(mode split same-brigade false-prefix eof deferred flush)
    add_test(NAME rum-streaming-${mode} COMMAND rum_streaming_tests ${mode})
    set_tests_properties(rum-streaming-${mode} PROPERTIES TIMEOUT 10)
  endforeach()
endif()
