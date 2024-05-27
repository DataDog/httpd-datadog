
add_library(
  mod_datadog
  SHARED
  src/mod_datadog.cpp
  src/tracing/conf.cpp
  src/tracing/hooks.cpp
)

target_include_directories(
  mod_datadog
  PUBLIC
  src
)

target_compile_options(mod_datadog
  PRIVATE -Wall -Wextra
)

add_dependencies(mod_datadog dd_trace_cpp-objects httpd fmt)

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
    dd_trace_cpp-objects 
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
