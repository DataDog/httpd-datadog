Include(FetchContent)

FetchContent_Declare(
  Catch2
  GIT_REPOSITORY https://github.com/catchorg/Catch2.git
  GIT_TAG        v2.13.9
)

FetchContent_MakeAvailable(Catch2)

add_executable(tests main.cpp test_utils.cpp)

target_include_directories(tests PRIVATE ${CMAKE_SOURCE_DIR}/mod_datadog/src)

# httpd and fmt are header-only here: utils.h includes <httpd.h> and
# <fmt/core.h>, and the one function needing httpd symbols
# (make_httpd_version -> ap_get_server_revision) is inline and untested, so
# nothing from httpd actually has to link.
target_link_libraries(tests PRIVATE Catch2::Catch2 httpd fmt)

add_test(NAME unit-tests COMMAND tests)
