# These checks use real APR pools. Cross builds need matching APR libraries.
find_library(TEST_APR_LIBRARY NAMES apr-1)
find_library(TEST_APRUTIL_LIBRARY NAMES aprutil-1)
if(TEST_APR_LIBRARY AND TEST_APRUTIL_LIBRARY AND NOT CMAKE_CROSSCOMPILING)
  add_executable(directory_lifetime_tests
    test_directory_lifetime.cpp
    ../../mod_datadog/src/common_conf.cpp)
  target_include_directories(directory_lifetime_tests PRIVATE
    ${CMAKE_SOURCE_DIR}/mod_datadog/src
    ${APACHE_INCLUDE_DIR} ${APR_INCLUDE_DIR})
  target_link_libraries(directory_lifetime_tests PRIVATE
    httpd dd-trace-cpp-static ${TEST_APR_LIBRARY} ${TEST_APRUTIL_LIBRARY})
  target_compile_options(directory_lifetime_tests PRIVATE
    -UNDEBUG -fsanitize=address -fno-omit-frame-pointer)
  target_link_options(directory_lifetime_tests PRIVATE -fsanitize=address)
  if(HTTPD_DATADOG_ENABLE_RUM)
    target_compile_definitions(directory_lifetime_tests PRIVATE HTTPD_DD_RUM)
    target_sources(directory_lifetime_tests PRIVATE
      ../../mod_datadog/src/rum/config.cpp)
    target_link_libraries(directory_lifetime_tests PRIVATE
      inject_browser_sdk_ffi fmt rapidjson)
  endif()
  add_test(NAME directory-lifetime COMMAND directory_lifetime_tests)
endif()
