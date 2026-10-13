Include(FetchContent)
enable_testing()

FetchContent_Declare(
  Catch2
  GIT_REPOSITORY https://github.com/catchorg/Catch2.git
  GIT_TAG        v2.13.9
)

FetchContent_MakeAvailable(Catch2)

add_executable(tests main.cpp test_utils.cpp ../rum/unit-test/test_rum_content_type.cpp)

target_include_directories(tests PRIVATE ${CMAKE_SOURCE_DIR}/mod_datadog/src)

# httpd and fmt are only needed for the headers of utils.h.
target_link_libraries(tests PRIVATE Catch2::Catch2 httpd fmt)

file(GLOB regression_checks CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/*_checks.cmake")
foreach(check_file IN LISTS regression_checks)
  include(${check_file})
endforeach()
