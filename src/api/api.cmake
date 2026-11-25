# API libraries, source lists and independent tools; included before runtime.cmake.
# Keep this file in src/api so CMAKE_CURRENT_LIST_DIR retains its original meaning.

# --- routines ---

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

# The production bridge is part of scriptforge, so this links that exact result
# boundary against a tiny fake VM instead of duplicating it in a test stub.
if(UNIX AND NOT WIN32)
    set(KP_ROUTINE_LUAJIT "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a")
    add_executable(kp_routinetest "${KP_API_SRC_ROOT}/../tools/kp_routinetest.cpp")
    target_include_directories(kp_routinetest PRIVATE
        "${KP_API_SRC_ROOT}" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_routinetest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_routinetest PRIVATE -m32)
    add_dependencies(kp_routinetest scriptforge)
    target_link_libraries(kp_routinetest PRIVATE scriptforge "${KP_ROUTINE_LUAJIT}" m dl)
    # One runtime per process even when two copies of the library load
    # (proxy + KPM, preload + DT_NEEDED). Loads the real libscriptforge.so.
    add_executable(kp_singleinstance_test "${KP_API_SRC_ROOT}/../tools/kp_singleinstance_test.cpp")
    target_compile_options(kp_singleinstance_test PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_singleinstance_test PRIVATE -m32)
    target_compile_definitions(kp_singleinstance_test PRIVATE
        KP_RUNTIME_SO="$<TARGET_FILE:scriptforge>")
    target_link_libraries(kp_singleinstance_test PRIVATE dl)
    add_dependencies(kp_singleinstance_test scriptforge)
    add_test(NAME kp_singleinstance_test COMMAND kp_singleinstance_test)
    set_tests_properties(kp_singleinstance_test PROPERTIES LABELS "offline;deploy" TIMEOUT 60)

    add_test(NAME kp_routinetest COMMAND kp_routinetest)
    set_tests_properties(kp_routinetest PROPERTIES
        ENVIRONMENT "SCRIPTFORGE_NO_AUTOSTART=1")
endif()

# --- structs ---

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
# entity module. That is deliberate: kp.struct.at(address, name) has to work
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
# wait for it. Not guarded on `if(TARGET scriptforge)`: that target is defined by
# runtime.cmake, included AFTER this fragment, so the guard is always false
# here regardless of whether scriptforge ends up existing. Unguarded still
# resolves correctly -- add_dependencies matches target names at generate
# time, once every include() in this directory has run, not at the line
# where it is called -- and scriptforge itself is unconditional on any UNIX
# host, the only host this top-level CMakeLists.txt is ever configured on.
add_dependencies(kp_structs scriptforge)

# --- kp_structtest -----------------------------------------------------------
#
# The harness runs, so it is built only where it can run: native 32-bit Linux.
# -no-pie because it hands its own buffer addresses to Lua as 32-bit numbers and
# then compares what came back; a PIE build would still work, but the addresses
# printed in the output would move every run and stop being readable evidence.
#
# Gated on UNIX alone, not on the LuaJIT archive existing yet or on
# `TARGET scriptforge`: both were checked at configure time, when the archive is
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
    add_dependencies(kp_structtest scriptforge)

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
        COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
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

# --- entity ---

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
# by `if(TARGET scriptforge)` -- which is always false at this point in the
# script, since runtime.cmake (where scriptforge is defined) is included AFTER
# this fragment in CMakeLists.txt, despite its comment claiming the API
# fragments are order-independent. Unguarded works: add_dependencies resolves
# target names at generate time, once every include() has run, not eagerly --
# proven against a two-target CMake project before relying on it here. scriptforge
# itself is unconditional on any UNIX host, which is the only host this
# top-level CMakeLists.txt is ever configured on.
add_dependencies(kp_entity scriptforge)

# --- kp_entitytest -----------------------------------------------------------
#
# The harness runs, so it is built only where it can run: native 32-bit Linux.
# It deliberately links kp_entity and its own fake dispatcher and nothing else.
# Adding a real routines target here would give the linker two definitions of
# kp::api::call and break both modules at once.
# Gated on UNIX alone, not on the LuaJIT archive existing yet or on
# `TARGET scriptforge`: both were checked at configure time, when the archive is
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
    add_dependencies(kp_entitytest scriptforge)

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
        COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
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

# --- support ---

set(KP_API_DIR      "${CMAKE_CURRENT_LIST_DIR}")
set(KP_API_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_API_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")

set(KP_SUPPORT_SOURCES
    "${KP_API_DIR}/output.cpp"
    "${KP_API_DIR}/timers.cpp"
    "${KP_API_DIR}/strings.cpp"
)

# LuaJIT headers only. The module never calls a Lua function the linker has to
# resolve at this level -- it is compiled into whatever binary already carries
# the interpreter, which is scriptforge.dll or libscriptforge.so.
set(KP_SUPPORT_LUA_INC "${CMAKE_SOURCE_DIR}/third_party/luajit/src")

add_library(kp_support STATIC ${KP_SUPPORT_SOURCES})
target_include_directories(kp_support PUBLIC "${KP_API_SRC_ROOT}"
                                             "${KP_SUPPORT_LUA_INC}")
target_compile_options(kp_support PUBLIC -m32 -Wall -Wextra)
target_link_options(kp_support PUBLIC -m32)

# --- kp_supporttest ----------------------------------------------------------
#
# The offline proof: tokenising, timer firing, timer removal, and a throwing
# timer taking its script into quarantine. It runs the real lua::Host, so it
# needs a linkable interpreter, which on this machine means the native 32-bit
# LuaJIT that src/runtime/runtime.cmake builds into the build tree. The Windows
# libluajit.a in third_party is PE-COFF and cannot be linked here.
#
# The dependency is taken from the scriptforge target, not from the archive path: a
# custom-command OUTPUT belongs to the fragment that declared it, and claiming
# the same output twice is a generator error rather than a shared rule.
#
# Not gated on `TARGET scriptforge` here, despite the reasoning above: that check
# is always false at this point in the script, since runtime.cmake (where
# scriptforge is defined) is included AFTER this fragment in CMakeLists.txt. That
# silently skipped this whole target on every from-scratch configure -- the
# STATUS message below used to fire unconditionally, never the executable.
# add_dependencies still resolves the target correctly: CMake matches
# dependency names at generate time, once every include() in this directory
# has run, not eagerly at the line where add_dependencies is called.
set(KP_SUPPORT_LUAJIT "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a")

if(UNIX AND NOT WIN32)
    add_executable(kp_supporttest
        "${KP_API_TOOLS}/kp_supporttest.cpp"
        ${KP_SUPPORT_SOURCES}
        "${KP_API_SRC_ROOT}/lua/host.cpp"
        "${KP_API_SRC_ROOT}/lua/value.cpp"
        "${KP_API_SRC_ROOT}/platform/platform.cpp"
        "${KP_API_SRC_ROOT}/platform/platform_linux.cpp"
    )
    # Sources rather than a link against kp_support and kp_hooks: those are
    # built without -fPIC and the tool is a plain executable, so compiling the
    # four files it actually needs is cheaper than pulling in the hook engine.
    target_include_directories(kp_supporttest PRIVATE
        "${KP_API_SRC_ROOT}" "${CMAKE_BINARY_DIR}/luajit32/src")
    target_compile_options(kp_supporttest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_supporttest PRIVATE -m32)
    add_dependencies(kp_supporttest scriptforge)
    target_link_libraries(kp_supporttest PRIVATE "${KP_SUPPORT_LUAJIT}" m dl)

    # Self-contained: writes its own scratch scripts to a temp dir (removed and
    # recreated each run) and exits on api::timers::pending() == 0.
    add_test(NAME kp_supporttest COMMAND kp_supporttest)

    add_executable(kp_namespacetest "${KP_API_TOOLS}/kp_namespacetest.cpp")
    target_include_directories(kp_namespacetest PRIVATE
        "${KP_API_SRC_ROOT}" "${KP_SUPPORT_LUA_INC}")
    target_compile_options(kp_namespacetest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_namespacetest PRIVATE -m32)
    target_link_libraries(kp_namespacetest PRIVATE scriptforge "${KP_SUPPORT_LUAJIT}" m dl)
    add_test(NAME kp_namespacetest.k1 COMMAND kp_namespacetest)
    add_test(NAME kp_namespacetest.k2 COMMAND kp_namespacetest k2)
    set_tests_properties(kp_namespacetest.k1 kp_namespacetest.k2 PROPERTIES
        ENVIRONMENT "SCRIPTFORGE_NO_AUTOSTART=1")
endif()

# --- the Windows half --------------------------------------------------------
#
# Compiled, not linked, mirroring image_win32 and hooks_win32: one configure
# proves both toolchains still accept these three files.
if(NOT KP_MINGW_CXX)
    find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
endif()

if(KP_MINGW_CXX)
    set(KP_SUPPORT_WIN32_OBJDIR "${CMAKE_BINARY_DIR}/win32")
    set(KP_SUPPORT_WIN32_OBJECTS)
    foreach(src ${KP_SUPPORT_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        set(obj "${KP_SUPPORT_WIN32_OBJDIR}/api_${name}.obj")
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_SUPPORT_WIN32_OBJDIR}
            COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                    ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
                    -I${KP_API_SRC_ROOT} -I${KP_SUPPORT_LUA_INC}
                    -c ${src} -o ${obj}
            DEPENDS ${src}
            COMMENT "i686-w64-mingw32-g++ ${name}.cpp"
            VERBATIM)
        list(APPEND KP_SUPPORT_WIN32_OBJECTS ${obj})
    endforeach()
    add_custom_target(support_win32 ALL DEPENDS ${KP_SUPPORT_WIN32_OBJECTS})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: the support module's "
                    "Windows half is not being compiled")
endif()

# --- vector ---

set(KP_VEC_API_DIR  "${CMAKE_CURRENT_LIST_DIR}")
set(KP_VEC_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_VEC_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")
set(KP_VEC_LUAJIT   "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a")

if(UNIX AND NOT WIN32)
    add_executable(kp_vectortest
        "${KP_VEC_TOOLS}/kp_vectortest.cpp"
        "${KP_VEC_API_DIR}/vector.cpp"
    )
    target_compile_features(kp_vectortest PRIVATE cxx_std_20)
    target_include_directories(kp_vectortest PRIVATE
        "${KP_VEC_SRC_ROOT}" "${CMAKE_BINARY_DIR}/luajit32/src")
    target_compile_options(kp_vectortest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_vectortest PRIVATE -m32)
    add_dependencies(kp_vectortest scriptforge)
    target_link_libraries(kp_vectortest PRIVATE scriptforge "${KP_VEC_LUAJIT}" m dl)
    add_test(NAME kp_vectortest COMMAND kp_vectortest)
    set_tests_properties(kp_vectortest PROPERTIES
        ENVIRONMENT "SCRIPTFORGE_NO_AUTOSTART=1")
endif()

# --- motion ---

if(UNIX AND NOT WIN32)
    add_executable(kp_motiontest "${CMAKE_SOURCE_DIR}/tools/kp_motiontest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/motion.cpp" "${CMAKE_CURRENT_LIST_DIR}/motion_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/motion_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/motion_lua.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/engine_gate.cpp")
    target_include_directories(kp_motiontest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_motiontest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_motiontest PRIVATE -m32)
    target_link_libraries(kp_motiontest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_motiontest scriptforge)
    # The argument is the source root: the test cross-checks the generated
    # data/addresses/k1_gog_103.json and data/routines/*.json read-only.
    add_test(NAME kp_motiontest COMMAND kp_motiontest "${CMAKE_SOURCE_DIR}")
    set_tests_properties(kp_motiontest PROPERTIES LABELS "offline;motion")

    # The engine-thread gate on its own, including a real second thread.
    add_executable(kp_enginegatetest "${CMAKE_SOURCE_DIR}/tools/kp_enginegatetest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/engine_gate.cpp")
    target_include_directories(kp_enginegatetest PRIVATE "${CMAKE_SOURCE_DIR}/src")
    target_compile_options(kp_enginegatetest PRIVATE -m32 -Wall -Wextra -pthread)
    target_link_options(kp_enginegatetest PRIVATE -m32 -pthread)
    add_test(NAME kp_enginegatetest COMMAND kp_enginegatetest)
    set_tests_properties(kp_enginegatetest PROPERTIES LABELS "offline;motion")
endif()
