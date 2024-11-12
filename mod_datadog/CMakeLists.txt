
add_library(
  mod_datadog
  SHARED
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

