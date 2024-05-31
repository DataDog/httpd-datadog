add_subdirectory(dd-trace-cpp)

# inject-browser-sdk
set(injector_static_lib ${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/lib/target/release/libinjectbrowsersdk.a)
set_source_files_properties(${injector_static_lib} PROPERTIES GENERATED TRUE)

add_custom_command(
  OUTPUT ${injector_static_lib}
  COMMAND cargo build --release
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/lib
  COMMENT "Building inject-browser-sdk static lib"
)

add_custom_target(build-injector DEPENDS ${injector_static_lib})

add_library(inject-browser-sdk STATIC IMPORTED GLOBAL)

add_dependencies(inject-browser-sdk build-injector)

set_property(
  TARGET inject-browser-sdk
  PROPERTY IMPORTED_LOCATION ${injector_static_lib}
)

target_include_directories(inject-browser-sdk
  INTERFACE
  ${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/injector_IIS/lib
)
