add_subdirectory(dd-trace-cpp)

# Force POSITION_INDEPENDENT_CODE (PIC) because mod_datadog.so is loaded via
# dlopen, but dd-trace-cpp sets this based on BUILD_SHARED_LIBS, whereas we
# link with the static library.
set_target_properties(dd-trace-cpp-objects PROPERTIES POSITION_INDEPENDENT_CODE ON)
