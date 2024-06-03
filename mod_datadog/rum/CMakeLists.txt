add_library(rum_module OBJECT)

add_dependencies(rum_module httpd inject-browser-sdk)

set_property(TARGET rum_module PROPERTY POSITION_INDEPENDENT_CODE ON)

target_sources(rum_module
  PRIVATE
    src/filter.cpp
    src/configuration.cpp
)

target_include_directories(rum_module
  PUBLIC
    include
  PRIVATE
    httpd
    injectbrowsersdk
    ${CMAKE_SOURCE_DIR}/mod_datadog/include/
)

target_link_libraries(rum_module httpd inject-browser-sdk)
