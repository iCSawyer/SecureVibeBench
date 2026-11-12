# Use the same GoogleTest source in online preparation and offline tests.
include(ExternalProject)

function(ExternalProject_Add name)
  if(name STREQUAL "googletest")
    cmake_parse_arguments(SVB "" "GIT_TAG" "" ${ARGN})
    _ExternalProject_Add(${name} ${SVB_UNPARSED_ARGUMENTS}
      GIT_TAG cbeab5d01811d23ea488efc07f2c31f7c53024e2
      UPDATE_DISCONNECTED TRUE)
  else()
    _ExternalProject_Add(${name} ${ARGN})
  endif()
endfunction()
