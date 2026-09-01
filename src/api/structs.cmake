# Build rules for the structs module, its generator and its offline harness.
#
# An include() fragment in the house style of src/hooks/hooks.cmake and
# src/api/entity.cmake. The top-level CMakeLists is owned elsewhere and is not
# edited by this module, so nothing here runs until someone adds
#
#     include(${CMAKE_SOURCE_DIR}/src/api/structs.cmake)
#
# after runtime.cmake -- after, because the harness links the native 32-bit
# LuaJIT that runtime.cmake builds. Paths come from CMAKE_CURRENT_LIST_DIR, the
# directory of THIS file, so the include site can be anywhere.

set(KP_STRUCTS_DIR      "${CMAKE_CURRENT_LIST_DIR}")
set(KP_STRUCTS_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_STRUCTS_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")
set(KP_STRUCTS_REPO     "${CMAKE_CURRENT_LIST_DIR}/../..")

# LuaJIT, twice: the Windows archive that ships in third_party and the native
# 32-bit one runtime.cmake builds into the build tree. Only the headers are
# needed to compile; the harness links the native one.
set(KP_LUAJIT_WIN_DIR    "${KP_STRUCTS_REPO}/third_party/luajit/src")
set(KP_LUAJIT_NATIVE_DIR "${CMAKE_BINARY_DIR}/luajit32/src")

# --- the generated layout table ----------------------------------------------
#
# src/generated/structs_k1.inc is checked in, because the runtime must build on
# a machine that has no Python. This rule regenerates it when the research file
# or the generator changes, so a data edit cannot be forgotten. The generator
# writes into the source tree on purpose: the .inc is an artifact people read
# and diff, not a build intermediate.
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
    add_custom_command(
        OUTPUT "${KP_STRUCTS_REPO}/src/generated/structs_k1.inc"
        COMMAND ${Python3_EXECUTABLE} "${KP_STRUCTS_TOOLS}/gen_structs.py" --game k1
        DEPENDS "${KP_STRUCTS_TOOLS}/gen_structs.py"
                "${KP_STRUCTS_REPO}/data/research/phasor_structs.json"
        COMMENT "gen_structs.py --game k1"
        VERBATIM)
    add_custom_target(kp_structs_generated ALL
                      DEPENDS "${KP_STRUCTS_REPO}/src/generated/structs_k1.inc")
else()
    message(STATUS "python3 not found: src/generated/structs_k1.inc is used as checked in")
endif()

# --- the module --------------------------------------------------------------
#
# structs.cpp alone. It depends on the platform layer for the readability probe
# and the log, and on nothing else in the project -- no routine bridge, no
# entity module. That is deliberate: kotor.struct.at(address, name) has to work
# before anything installs an object resolver, so this library links against a
# game that has not started yet.
add_library(kp_structs STATIC "${KP_STRUCTS_DIR}/structs.cpp")
target_include_directories(kp_structs PUBLIC "${KP_STRUCTS_SRC_ROOT}"
                                             "${KP_LUAJIT_NATIVE_DIR}")
target_compile_options(kp_structs PUBLIC -m32 -Wall -Wextra)
target_link_options(kp_structs PUBLIC -m32)
if(TARGET kp_structs_generated)
    add_dependencies(kp_structs kp_structs_generated)
endif()
# Headers only, no link -- but they live in the build tree, written by
# runtime.cmake's custom command, and add_dependencies is what makes CMake
# wait for it. Not guarded on `if(TARGET kphasor)`: that target is defined by
# runtime.cmake, included AFTER this fragment, so the guard is always false
# here regardless of whether kphasor ends up existing. Unguarded still
# resolves correctly -- add_dependencies matches target names at generate
# time, once every include() in this directory has run, not at the line
# where it is called -- and kphasor itself is unconditional on any UNIX
# host, the only host this top-level CMakeLists.txt is ever configured on.
add_dependencies(kp_structs kphasor)

# --- kp_structtest -----------------------------------------------------------
#
# The harness runs, so it is built only where it can run: native 32-bit Linux.
# -no-pie because it hands its own buffer addresses to Lua as 32-bit numbers and
# then compares what came back; a PIE build would still work, but the addresses
# printed in the output would move every run and stop being readable evidence.
#
# Gated on UNIX alone, not on the LuaJIT archive existing yet or on
# `TARGET kphasor`: both were checked at configure time, when the archive is
# always absent (runtime.cmake's custom command that builds it hasn't run --
# it is a BUILD-time step) and the target guard has the same always-false
# ordering problem as kp_structs above. That silently skipped this whole
# target on every from-scratch configure. add_dependencies below is what
# actually establishes the build-time wait.
if(UNIX AND NOT WIN32)
    set(KP_LUAJIT_NATIVE_LIB "${KP_LUAJIT_NATIVE_DIR}/libluajit.a")
    add_executable(kp_structtest "${KP_STRUCTS_TOOLS}/kp_structtest.cpp")
    target_include_directories(kp_structtest PRIVATE "${KP_STRUCTS_SRC_ROOT}"
                                                     "${KP_LUAJIT_NATIVE_DIR}")
    target_link_libraries(kp_structtest PRIVATE kp_structs kp_hooks
                          "${KP_LUAJIT_NATIVE_LIB}" m dl)
    target_link_options(kp_structtest PRIVATE -no-pie)
    add_dependencies(kp_structtest kphasor)

    # Self-contained: exits 0 on kp_structtest's own g_failures == 0.
    add_test(NAME kp_structtest COMMAND kp_structtest)
endif()

# --- the Windows half --------------------------------------------------------
#
# Compiled, not linked, exactly as hooks.cmake and entity.cmake do it: the point
# is to catch a Windows-only compile break in the same `cmake --build` that
# builds the Linux half. The DLL that will consume this object links it from
# here once the runtime wires the host API in.
if(NOT KP_MINGW_CXX)
    find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
endif()

if(KP_MINGW_CXX)
    set(KP_STRUCTS_WIN32_OBJDIR "${CMAKE_BINARY_DIR}/win32")
    set(KP_STRUCTS_WIN32_OBJ "${KP_STRUCTS_WIN32_OBJDIR}/api_structs.obj")
    add_custom_command(
        OUTPUT ${KP_STRUCTS_WIN32_OBJ}
        COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_STRUCTS_WIN32_OBJDIR}
        COMMAND ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
                -I${KP_STRUCTS_SRC_ROOT} -I${KP_LUAJIT_WIN_DIR}
                -c "${KP_STRUCTS_DIR}/structs.cpp" -o ${KP_STRUCTS_WIN32_OBJ}
        DEPENDS "${KP_STRUCTS_DIR}/structs.cpp"
                "${KP_STRUCTS_REPO}/src/generated/structs_k1.inc"
        COMMENT "i686-w64-mingw32-g++ structs.cpp"
        VERBATIM)
    add_custom_target(api_structs_win32 ALL DEPENDS ${KP_STRUCTS_WIN32_OBJ})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: the structs module's "
                    "Windows half is not being compiled")
endif()
