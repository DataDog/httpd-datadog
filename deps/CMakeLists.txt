add_subdirectory(dd-trace-cpp)

if (HTTPD_DATADOG_ENABLE_RUM)
  corrosion_import_crate(MANIFEST_PATH ${CMAKE_SOURCE_DIR}/deps/inject-browser-sdk/lib/Cargo.toml)

  corrosion_experimental_cbindgen(
    TARGET injectbrowsersdk
    HEADER_NAME injectbrowsersdk.h
    FLAGS --config ${CMAKE_SOURCE_DIR}/deps/cbindgen.toml
  )
endif ()
