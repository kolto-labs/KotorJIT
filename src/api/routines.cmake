# Build rules for the NWScript engine-routine bridge.
#
# Same shape as the other src/api fragments: pulled in with
#     include(${CMAKE_SOURCE_DIR}/src/api/routines.cmake)
# and built from CMAKE_CURRENT_LIST_DIR so include ORDER does not matter.
#
# The bridge is compiled into whatever binary already carries the interpreter --
# kphasor.dll or libkphasor.so -- so nothing is linked here.

set(KP_API_DIR      "${CMAKE_CURRENT_LIST_DIR}")
set(KP_API_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")

set(KP_ROUTINE_SOURCES
    "${KP_API_DIR}/routines.cpp"
    "${KP_API_DIR}/enginestruct.cpp"
    CACHE INTERNAL "NWScript routine bridge sources")

# Generated tables are #included rather than compiled, so they have to be named
# as dependencies or a stale object survives a regeneration. This bit the
# project once already: a rebuilt event table left the DLL older than the table
# it was supposed to contain.
file(GLOB KP_ROUTINE_GENERATED "${KP_API_SRC_ROOT}/generated/routines_*.inc"
                               "${KP_API_SRC_ROOT}/generated/routine_defaults_*.inc")
set_source_files_properties(${KP_ROUTINE_SOURCES}
    PROPERTIES OBJECT_DEPENDS "${KP_ROUTINE_GENERATED}")
