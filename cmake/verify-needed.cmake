# Check the dynamic dependencies of LIBRARY, so it loads on glibc and musl:
# - It may only depend on the libraries below: glibc provides them, and musl
#   maps them to its own libc.
# - It must depend on libc.so.6. Otherwise, libc is likely linked statically.

set(allowed_libraries
    libc.so.6
    libdl.so.2
    libm.so.6
    libpthread.so.0)

execute_process(
    COMMAND "${READELF}" --dynamic "${LIBRARY}"
    OUTPUT_VARIABLE dynamic_section
    COMMAND_ERROR_IS_FATAL ANY)

string(REGEX MATCHALL
    "Shared library: \\[[^]]+\\]"
    needed_entries
    "${dynamic_section}")
foreach(entry IN LISTS needed_entries)
    string(REGEX REPLACE "Shared library: \\[([^]]+)\\]" "\\1" library "${entry}")
    if(NOT library IN_LIST allowed_libraries)
        message(FATAL_ERROR "${LIBRARY} needs a library that is not allowed: ${library}")
    endif()
endforeach()

if(NOT dynamic_section MATCHES "Shared library: \\[libc\\.so\\.6\\]")
    message(FATAL_ERROR "${LIBRARY} does not need libc.so.6: is libc linked statically?")
endif()
