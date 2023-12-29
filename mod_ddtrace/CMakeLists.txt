
add_library(
  mod_ddtrace
  SHARED
  src/mod_ddtrace.cpp
)

target_include_directories(
  mod_ddtrace
  PUBLIC
  include
)

target_compile_options(mod_ddtrace
  PRIVATE -Wall -Wextra
)

add_dependencies(mod_ddtrace dd_trace_cpp-objects)

target_include_directories(
  mod_ddtrace
  PRIVATE
    ${APACHE_INCLUDE_DIR}
    ${APR_INCLUDE_DIR}
)

set_target_properties(
  mod_ddtrace 
  PROPERTIES
    PREFIX ""
    SUFFIX ".so"
)

target_link_libraries(mod_ddtrace dd_trace_cpp-objects httpd)

if (APPLE)
  target_link_options(mod_ddtrace PRIVATE -undefined dynamic_lookup)
endif ()
