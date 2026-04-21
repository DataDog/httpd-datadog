include(${CMAKE_SOURCE_DIR}/cmake/deps/fmt.cmake)

add_subdirectory(dd-trace-cpp)

# Force POSITION_INDEPENDENT_CODE (PIC) because mod_datadog.so is loaded via
# dlopen, but dd-trace-cpp sets this based on BUILD_SHARED_LIBS, whereas we
# link with the static library.
set_target_properties(dd-trace-cpp-objects PROPERTIES POSITION_INDEPENDENT_CODE ON)

if (HTTPD_DATADOG_ENABLE_RUM)
  if (NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/inject-browser-sdk/CMakeLists.txt")
    message(FATAL_ERROR
      "deps/inject-browser-sdk submodule is not initialized. "
      "Run: git submodule update --init --recursive")
  endif ()
  # mod_datadog/CMakeLists.txt references ${injectbrowsersdk_SOURCE_DIR}, which
  # FetchContent used to set; replicate it for the submodule layout.
  set(injectbrowsersdk_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/inject-browser-sdk" CACHE INTERNAL "")
  add_subdirectory(inject-browser-sdk EXCLUDE_FROM_ALL)

  include(${CMAKE_SOURCE_DIR}/cmake/deps/rapidjson.cmake)
endif ()
