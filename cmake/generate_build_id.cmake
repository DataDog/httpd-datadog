# Generates a unique build identifier based on multiple criteria
# and sets the resulting identifier to the specified output variable.

# Description:
#   This function constructs a build identifier by considering the following factors:
#   1. If the build type is Debug, the identifier is prefix with "dev" and the current 
#      date in the format YYYYMMDD.
#   2. If a git command is available, the identifier includes the latest commit hash.
#      Else, the identifier includes the hostname of the machine.
#
#   The components of the identifier are joined with a hyphen (-).
#
# Parameters:
#   OUT_BUILD_ID:
#     The name of the variable where the generated build identifier will be stored.
function (make_build_id OUT_BUILD_ID)
  find_program(GIT_CMD "git")
  if (GIT_CMD)
    execute_process(
      COMMAND git log -1 --format=%h
      WORKING_DIRECTORY ${CMAKE_CURRENT_LIST_DIR}
      OUTPUT_VARIABLE GIT_HASH
      OUTPUT_STRIP_TRAILING_WHITESPACE
      RESULT_VARIABLE RC
    )

    if(NOT RC EQUAL 0)
      message(FATAL_ERROR "The command \"git log -1 --format=%h\" failed with exit code ${RC}")
    endif()

    set(${OUT_BUILD_ID} "dev+${GIT_HASH}" PARENT_SCOPE)
  else ()
    set(${OUT_BUILD_ID} "dev+${USER_HOSTNAME}" PARENT_SCOPE)
  endif()
endfunction ()
