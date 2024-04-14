add_subdirectory(rum)

add_library(
  mod_datadog
  SHARED
  src/mod_datadog.cpp
  src/utils.cpp
)

target_include_directories(
  mod_datadog
  PUBLIC
  include
)

target_compile_options(mod_datadog
  PRIVATE -Wall -Wextra
)

add_dependencies(mod_datadog dd_trace_cpp-objects httpd rum_module)

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

target_include_directories(mod_datadog PRIVATE httpd rum_module)
target_link_libraries(mod_datadog dd_trace_cpp-objects httpd rum_module)

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
