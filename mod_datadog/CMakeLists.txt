include(${CMAKE_SOURCE_DIR}/cmake/generate_build_id.cmake)

# Generate the build identifier.
# Known issue: this command is only run during the CMake configuration stage.
# Possible solution: <https://jonathanhamberg.com/post/cmake-embedding-git-hash/>
if (CMAKE_BUILD_TYPE MATCHES Debug)
  make_build_id(HTTPD_DATADOG_BUILD_ID)
  if (HTTPD_DATADOG_BUILD_ID)
    set(HTTPD_DATADOG_VERSION "${CMAKE_PROJECT_VERSION}-${HTTPD_DATADOG_BUILD_ID}")
  else ()
    set(HTTPD_DATADOG_VERSION "${CMAKE_PROJECT_VERSION}")
  endif ()
else ()
  set(HTTPD_DATADOG_VERSION "${CMAKE_PROJECT_VERSION}")
endif ()

message(STATUS "httpd-datadog version=[${HTTPD_DATADOG_VERSION}]")

add_library(
  mod_datadog
  SHARED
    ${CMAKE_BINARY_DIR}/version.cpp
    src/mod_datadog.cpp
    src/common_conf.cpp
    src/tracing/conf.cpp
    src/tracing/hooks.cpp
)

set_property(TARGET mod_datadog PROPERTY POSITION_INDEPENDENT_CODE ON)

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
      src/rum/telemetry.cpp
  )

  target_link_libraries(
    mod_datadog
    PRIVATE
      inject_browser_sdk_ffi 
      rapidjson
  )

  execute_process (
    COMMAND cargo pkgid --package inject-browser-sdk --manifest-path "${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/Cargo.toml"
    OUTPUT_VARIABLE RUM_SDK_INJECTOR_PKGID
  )

  string(REGEX REPLACE ".*@" "" _VERSION_STRING_CANDIDATE "${RUM_SDK_INJECTOR_PKGID}")
  if(_VERSION_STRING_CANDIDATE MATCHES "([0-9]+\\.[0-9]+\\.[0-9]+)")
    set(RUM_SDK_INJECTOR_VERSION "${CMAKE_MATCH_1}")
  else()
    message(FATAL_ERROR "Could not extract a maj.min.patch version from string: '${_VERSION_STRING_CANDIDATE}' derived from PkgID: '${RUM_SDK_INJECTOR_PKGID}'")
  endif()
  string(STRIP "${RUM_SDK_INJECTOR_VERSION}" RUM_SDK_INJECTOR_VERSION)

  unset(_VERSION_STRING_CANDIDATE)
  unset(RUM_SDK_INJECTOR_PKGID)
endif ()

configure_file(src/version.cpp.in ${CMAKE_BINARY_DIR}/version.cpp)

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

if(HTTPD_DATADOG_ENABLE_COVERAGE)
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "HTTPD_DATADOG_ENABLE_COVERAGE is only supported with clang")
  else()
    target_compile_options(mod_datadog
      PRIVATE
        -fprofile-instr-generate 
        -fcoverage-mapping 
        -mllvm 
        -runtime-counter-relocation=true
    )
    target_link_options(mod_datadog
      PRIVATE
        -fprofile-instr-generate 
        -mllvm 
        -runtime-counter-relocation=true
    )
  endif()
endif ()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(LINKER_SCRIPT ${CMAKE_CURRENT_LIST_DIR}/symbols.ld)
  set_target_properties(mod_datadog PROPERTIES LINK_DEPENDS ${LINKER_SCRIPT})
  target_link_options(mod_datadog PRIVATE "-Wl,--version-script=${LINKER_SCRIPT}")
elseif(CMAKE_SYSTEM_NAME STREQUAL "Darwin")
  if(CMAKE_COMPILER_IS_GNUCXX OR (CMAKE_CXX_COMPILER_ID MATCHES "Clang"))
    target_link_options(mod_datadog PRIVATE -undefined dynamic_lookup)
  endif()

  set(EXPORTED_SYMBOLS ${CMAKE_CURRENT_LIST_DIR}/symbols.ld-prime)
  set_target_properties(mod_datadog PROPERTIES LINK_DEPENDS ${EXPORTED_SYMBOLS})
  target_link_options(mod_datadog PRIVATE "-Wl,-exported_symbols_list" "-Wl,${EXPORTED_SYMBOLS}")
endif()

if(HTTPD_DATADOG_PATCH_AWAY_LIBC)
  patch_away_libc(mod_datadog)
endif()

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

