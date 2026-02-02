add_subdirectory(dd-trace-cpp)

if (HTTPD_DATADOG_ENABLE_RUM)
  corrosion_import_crate(
    MANIFEST_PATH inject-browser-sdk/Cargo.toml
    CRATES inject-browser-sdk-ffi
  )

  corrosion_experimental_cbindgen(
    TARGET inject_browser_sdk_ffi
    HEADER_NAME injectbrowsersdk.h
    FLAGS --config ${CMAKE_SOURCE_DIR}/deps/cbindgen.toml
  )
endif ()
