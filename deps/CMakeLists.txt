add_subdirectory(dd-trace-cpp)

if (HTTPD_DATADOG_ENABLE_RUM)
  # Patch Cargo.toml to remove cdylib (unsupported on musl targets)
  execute_process(
    COMMAND sed -i.bak "s/\"cdylib\", //"
      ${CMAKE_CURRENT_SOURCE_DIR}/inject-browser-sdk/lib/inject-browser-sdk-ffi/Cargo.toml
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  )

  corrosion_import_crate(MANIFEST_PATH inject-browser-sdk/Cargo.toml)

  corrosion_experimental_cbindgen(
    TARGET inject_browser_sdk_ffi
    HEADER_NAME injectbrowsersdk.h
    FLAGS --config ${CMAKE_SOURCE_DIR}/deps/cbindgen.toml
  )
endif ()
