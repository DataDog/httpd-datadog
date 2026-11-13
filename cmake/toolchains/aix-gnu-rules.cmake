# CMake's native AIX helper invokes dump. Use the GNU cross linker.
foreach(language C CXX)
  set(CMAKE_${language}_ARCHIVE_CREATE "<CMAKE_AR> -X64 qc <TARGET> <LINK_FLAGS> <OBJECTS>")
  set(CMAKE_${language}_ARCHIVE_APPEND "<CMAKE_AR> -X64 q <TARGET> <LINK_FLAGS> <OBJECTS>")
  set(CMAKE_${language}_ARCHIVE_FINISH "<CMAKE_RANLIB> -X64 <TARGET>")
  set(CMAKE_${language}_USE_IMPLICIT_LINK_DIRECTORIES_IN_RUNTIME_PATH 0)
  set(CMAKE_${language}_LINK_FLAGS "")
  set(CMAKE_SHARED_LIBRARY_CREATE_${language}_FLAGS "")
  set(CMAKE_${language}_CREATE_SHARED_LIBRARY
    "<CMAKE_${language}_COMPILER> <CMAKE_SHARED_LIBRARY_${language}_FLAGS> <LANGUAGE_COMPILE_FLAGS> <LINK_FLAGS> -shared -o <TARGET> <OBJECTS> <LINK_LIBRARIES>")
endforeach()
set(CMAKE_PLATFORM_REQUIRED_RUNTIME_PATH "")
