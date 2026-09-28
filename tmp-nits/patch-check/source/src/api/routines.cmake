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

# The production bridge is part of kphasor, so this links that exact result
# boundary against a tiny fake VM instead of duplicating it in a test stub.
if(UNIX AND NOT WIN32)
    set(KP_ROUTINE_LUAJIT "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a")
    add_executable(kp_routinetest "${KP_API_SRC_ROOT}/../tools/kp_routinetest.cpp")
    target_include_directories(kp_routinetest PRIVATE
        "${KP_API_SRC_ROOT}" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_routinetest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_routinetest PRIVATE -m32)
    add_dependencies(kp_routinetest kphasor)
    target_link_libraries(kp_routinetest PRIVATE kphasor "${KP_ROUTINE_LUAJIT}" m dl)
    add_test(NAME kp_routinetest COMMAND kp_routinetest)
endif()
