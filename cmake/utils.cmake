function(split_debug_info target_name)
  set(debug_file "$<TARGET_FILE:${target_name}>.debug")

  if (CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_custom_command(TARGET ${target_name} POST_BUILD
        COMMAND ${CMAKE_OBJCOPY} --only-keep-debug $<TARGET_FILE:${target_name}> ${debug_file}
        COMMAND ${CMAKE_STRIP} --strip-debug --strip-unneeded $<TARGET_FILE:${target_name}>
        COMMAND ${CMAKE_OBJCOPY} --add-gnu-debuglink=${debug_file} $<TARGET_FILE:${target_name}>
        COMMENT "Created debug symbol ${debug_file}"
    )
  install(FILES ${debug_file} DESTINATION lib)
  elseif (CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    find_program(DSYMUTIL_PROGRAM dsymutil)
    if (NOT DSYMUTIL_PROGRAM)
      message(WARNING "dsymutil program not found. Debug info will not be split.")
    else ()
      add_custom_command(TARGET ${target_name} POST_BUILD
        COMMAND ${DSYMUTIL_PROGRAM} $<TARGET_FILE:${target_name}> --out ${debug_file}
        COMMENT "Created debug symbol ${debug_file}"
      )
      install(FILES ${debug_file} DESTINATION lib)
    endif()
  endif()
endfunction()

function(patch_away_libc target)
  if (CMAKE_SYSTEM_NAME STREQUAL Darwin)
    return()
  endif()

  find_program(PATCHELF patchelf)
  if (PATCHELF STREQUAL "PATCHELF-NOTFOUND")
    message(WARNING "Patchelf not found. Can't build glibc + musl binaries")
  else()
    add_custom_command(TARGET ${target} POST_BUILD
        COMMAND patchelf --remove-needed libc.musl-${CMAKE_SYSTEM_PROCESSOR}.so.1 $<TARGET_FILE:${target}>)
  endif()
endfunction()
