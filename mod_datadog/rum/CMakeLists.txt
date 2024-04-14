# TODO: don't know why it doesnt use inject-browser-sdk CMakeLists.txt
add_library(injectbrowsersdk STATIC IMPORTED)

set_property(
  TARGET injectbrowsersdk 
  PROPERTY 
    # IMPORTED_LOCATION "${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/libinjectbrowsersdk.dylib"
    IMPORTED_LOCATION "/Users/damien.mehala/workspace/inject-browser-sdk/nginx-dd-rum/deps/inject-browser-sdk/release/libinjectbrowsersdk.a"
)

target_include_directories(
  injectbrowsersdk
  INTERFACE
  ${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/
  ${CMAKE_SOURCE_DIR}/mod_datadog/include/
)

add_library(rum_module OBJECT)

add_dependencies(rum_module httpd)
#inject-browser-sdk)

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
)

target_link_libraries(rum_module httpd injectbrowsersdk)
