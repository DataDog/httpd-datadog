Include(FetchContent)

FetchContent_Declare(
  Catch2
  GIT_REPOSITORY https://github.com/catchorg/Catch2.git
  GIT_TAG        v2.13.9
)

FetchContent_MakeAvailable(Catch2)

add_executable(tests main.cpp test_utils.cpp)

target_include_directories(tests PRIVATE ${CMAKE_SOURCE_DIR}/mod_datadog/src)

# utils.h uses headers supplied by the httpd and fmt targets.
target_link_libraries(tests PRIVATE Catch2::Catch2 httpd fmt)

add_test(NAME unit-tests COMMAND tests)
