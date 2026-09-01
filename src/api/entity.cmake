# Build rules for the entity module and its offline harness.
#
# An include() fragment in the house style of src/hooks/hooks.cmake. The
# top-level CMakeLists is owned elsewhere and is not edited by this module, so
# nothing here runs until someone adds
#
#     include(${CMAKE_SOURCE_DIR}/src/api/entity.cmake)
#
# after runtime.cmake -- after, because the harness links the native 32-bit
# LuaJIT that runtime.cmake builds. Paths come from CMAKE_CURRENT_LIST_DIR, the
# directory of THIS file, so the include site can be anywhere.

set(KP_API_DIR      "${CMAKE_CURRENT_LIST_DIR}")
set(KP_API_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_API_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")

# LuaJIT, twice: the Windows archive that ships in third_party, and the native
# 32-bit one runtime.cmake builds into the build tree. Only the headers are
# needed to compile; the harness links the native one.
set(KP_LUAJIT_WIN_DIR   "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
set(KP_LUAJIT_NATIVE_DIR "${CMAKE_BINARY_DIR}/luajit32/src")

# --- the module --------------------------------------------------------------
#
# entity.cpp alone. It calls kp::api::find/call/binding as api/routines.hpp
# declares them, so this library does not link on its own: whatever links it
# supplies the routine bridge -- src/api/routines.cpp in the runtime, the fake
# dispatcher in the harness below. That is the seam, and it is why this is a
# static library rather than a source added to some other target.
add_library(kp_entity STATIC "${KP_API_DIR}/entity.cpp")
target_include_directories(kp_entity PUBLIC "${KP_API_SRC_ROOT}"
                                            "${KP_LUAJIT_NATIVE_DIR}")
target_compile_options(kp_entity PUBLIC -m32 -Wall -Wextra)
target_link_options(kp_entity PUBLIC -m32)
# Headers only, no link -- but the headers live in the build tree, written by
# runtime.cmake's custom command, and CMake only infers that ordering from a
# real dependency edge. kp_entitytest already tries to declare this, guarded
# by `if(TARGET kphasor)` -- which is always false at this point in the
# script, since runtime.cmake (where kphasor is defined) is included AFTER
# this fragment in CMakeLists.txt, despite its comment claiming the API
# fragments are order-independent. Unguarded works: add_dependencies resolves
# target names at generate time, once every include() has run, not eagerly --
# proven against a two-target CMake project before relying on it here. kphasor
# itself is unconditional on any UNIX host, which is the only host this
# top-level CMakeLists.txt is ever configured on.
add_dependencies(kp_entity kphasor)

# --- kp_entitytest -----------------------------------------------------------
#
# The harness runs, so it is built only where it can run: native 32-bit Linux.
# It deliberately links kp_entity and its own fake dispatcher and nothing else.
# Adding a real routines target here would give the linker two definitions of
# kp::api::call and break both modules at once.
# Gated on UNIX alone, not on the LuaJIT archive existing yet or on
# `TARGET kphasor`: both were checked at configure time, when the archive is
# always absent (it is a build-time output) and the target guard has the same
# always-false ordering problem kp_entity's own dependency had above. That
# silently skipped this whole target on every from-scratch configure.
if(UNIX AND NOT WIN32)
    set(KP_LUAJIT_NATIVE_LIB "${KP_LUAJIT_NATIVE_DIR}/libluajit.a")
    add_executable(kp_entitytest "${KP_API_TOOLS}/kp_entitytest.cpp")
    target_include_directories(kp_entitytest PRIVATE "${KP_API_SRC_ROOT}"
                                                     "${KP_LUAJIT_NATIVE_DIR}")
    target_link_libraries(kp_entitytest PRIVATE kp_entity
                          "${KP_LUAJIT_NATIVE_LIB}" m dl)
    add_dependencies(kp_entitytest kphasor)

    # Print-and-inspect, not assertion-based (it always exits 0): registered as
    # a smoke test, so a crash or an uncaught Lua error still fails the suite.
    add_test(NAME kp_entitytest COMMAND kp_entitytest)
endif()

# --- the Windows half --------------------------------------------------------
#
# Compiled, not linked, exactly as hooks.cmake does it: the point is to catch a
# Windows-only compile break in the same `cmake --build` that builds the Linux
# half. The DLL that will consume this object links it from here once the
# routine bridge exists.
if(NOT KP_MINGW_CXX)
    find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
endif()

if(KP_MINGW_CXX)
    set(KP_API_WIN32_OBJDIR "${CMAKE_BINARY_DIR}/win32")
    set(KP_API_WIN32_OBJ "${KP_API_WIN32_OBJDIR}/api_entity.obj")
    add_custom_command(
        OUTPUT ${KP_API_WIN32_OBJ}
        COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_API_WIN32_OBJDIR}
        COMMAND ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
                -I${KP_API_SRC_ROOT} -I${KP_LUAJIT_WIN_DIR}
                -c "${KP_API_DIR}/entity.cpp" -o ${KP_API_WIN32_OBJ}
        DEPENDS "${KP_API_DIR}/entity.cpp"
        COMMENT "i686-w64-mingw32-g++ entity.cpp"
        VERBATIM)
    add_custom_target(api_entity_win32 ALL DEPENDS ${KP_API_WIN32_OBJ})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: the entity module's "
                    "Windows half is not being compiled")
endif()
