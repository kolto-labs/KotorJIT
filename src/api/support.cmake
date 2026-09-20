# Build rules for the support module: output, timers and strings.
#
# An include() fragment in the house style of src/hooks/hooks.cmake. The
# top-level CMakeLists is owned elsewhere, so everything here is written to be
# pulled in with
#
#     include(${CMAKE_SOURCE_DIR}/src/api/support.cmake)
#
# from anywhere, and paths are built from CMAKE_CURRENT_LIST_DIR (this file's
# directory) rather than CMAKE_CURRENT_SOURCE_DIR.
#
# Nothing here assumes an include ORDER either. The fragment is guarded on what
# it finds rather than on variables another fragment happens to have set, so
# including it before or after src/runtime/runtime.cmake gives the same result.

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
# the interpreter, which is kphasor.dll or libkphasor.so.
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
# The dependency is taken from the kphasor target, not from the archive path: a
# custom-command OUTPUT belongs to the fragment that declared it, and claiming
# the same output twice is a generator error rather than a shared rule.
#
# Not gated on `TARGET kphasor` here, despite the reasoning above: that check
# is always false at this point in the script, since runtime.cmake (where
# kphasor is defined) is included AFTER this fragment in CMakeLists.txt. That
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
    add_dependencies(kp_supporttest kphasor)
    target_link_libraries(kp_supporttest PRIVATE "${KP_SUPPORT_LUAJIT}" m dl)

    # Self-contained: writes its own scratch scripts to a temp dir (removed and
    # recreated each run) and exits on api::timers::pending() == 0.
    add_test(NAME kp_supporttest COMMAND kp_supporttest)

    add_executable(kp_namespacetest "${KP_API_TOOLS}/kp_namespacetest.cpp")
    target_include_directories(kp_namespacetest PRIVATE
        "${KP_API_SRC_ROOT}" "${KP_SUPPORT_LUA_INC}")
    target_compile_options(kp_namespacetest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_namespacetest PRIVATE -m32)
    target_link_libraries(kp_namespacetest PRIVATE kphasor "${KP_SUPPORT_LUAJIT}" m dl)
    add_test(NAME kp_namespacetest.k1 COMMAND kp_namespacetest)
    add_test(NAME kp_namespacetest.k2 COMMAND kp_namespacetest k2)
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
