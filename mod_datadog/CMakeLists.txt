
add_library(
  mod_datadog
  SHARED
    src/mod_datadog.cpp
    src/common_conf.cpp
    src/tracing/conf.cpp
    src/tracing/hooks.cpp
    src/crash-tracker/conf.cpp
    src/crash-tracker/hook.cpp
)

if (HTTPD_DATADOG_ENABLE_RUM)
  target_compile_definitions(
    mod_datadog
    PRIVATE 
      HTTPD_DD_RUM
  )

  target_sources(
    mod_datadog
    PRIVATE
      src/rum/config.cpp
      src/rum/filter.cpp
  )

  target_link_libraries(
    mod_datadog
    PRIVATE
      injectbrowsersdk
      rapidjson
  )
endif ()

target_include_directories(
  mod_datadog
  PUBLIC
  src
)

target_compile_options(mod_datadog
  PRIVATE -Wall -Wextra
)

add_dependencies(mod_datadog dd_trace_cpp-static httpd fmt)

target_include_directories(
  mod_datadog
  PRIVATE
    ${APACHE_INCLUDE_DIR}
    ${APR_INCLUDE_DIR}
)

set_target_properties(
  mod_datadog
  PROPERTIES
    PREFIX ""
    SUFFIX ".so"
)

target_include_directories(mod_datadog PRIVATE httpd)

target_link_libraries(mod_datadog 
  PRIVATE
    dd_trace_cpp-static 
    httpd 
    fmt
)

if (HTTPD_DATADOG_ENABLE_COVERAGE)
  target_compile_options(mod_datadog
    PRIVATE
      -ftest-coverage
      -g
      -O0
      -fprofile-arcs
  )
  target_link_libraries(mod_datadog
    PRIVATE
     -fprofile-arcs
  )
endif ()

if (APPLE)
  target_link_options(mod_datadog PRIVATE -undefined dynamic_lookup)
endif ()

install(
  TARGETS mod_datadog
  DESTINATION lib
  # Maybe
  # LIBRARY lib
  # FRAMEWORK lib
  # RUNTIME lib
)
if(CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
  split_debug_info(mod_datadog)
endif()
