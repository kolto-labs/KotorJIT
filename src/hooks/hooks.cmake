# Build rules for the detour engine and the platform layer it sits on.
#
# This is an include() fragment, not a subdirectory: the top-level CMakeLists is
# owned elsewhere, so everything here is written to be pulled in with
#
#     include(${CMAKE_SOURCE_DIR}/src/hooks/hooks.cmake)
#
# from anywhere. That is why paths are built from CMAKE_CURRENT_LIST_DIR (the
# directory of THIS file) rather than CMAKE_CURRENT_SOURCE_DIR (the directory of
# whichever CMakeLists is doing the including).

set(KP_HOOKS_DIR     "${CMAKE_CURRENT_LIST_DIR}")
set(KP_PLATFORM_DIR  "${CMAKE_CURRENT_LIST_DIR}/../platform")
set(KP_SRC_DIR       "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_TOOLS_DIR     "${CMAKE_CURRENT_LIST_DIR}/../../tools")

add_library(kp_hooks STATIC
    "${KP_HOOKS_DIR}/trampoline.cpp"
    "${KP_HOOKS_DIR}/registry.cpp"
    "${KP_PLATFORM_DIR}/platform.cpp"
)

# The one place a platform is chosen. Everything above this line is byte
# manipulation and knows nothing about the OS.
if(WIN32)
    target_sources(kp_hooks PRIVATE "${KP_PLATFORM_DIR}/platform_win32.cpp")
else()
    target_sources(kp_hooks PRIVATE "${KP_PLATFORM_DIR}/platform_linux.cpp")
endif()

# Includes are rooted at src/, so headers read as "hooks/trampoline.hpp" and
# "platform/platform.hpp" -- the module they belong to is visible at the include
# site rather than implied by directory context.
target_include_directories(kp_hooks PUBLIC "${KP_SRC_DIR}")

# -m32 as a PUBLIC option on the target rather than a global setting or a
# pointer-size assertion, matching how kp_image is built in the top-level
# CMakeLists. The host toolchain configures as 64-bit, so a
# CMAKE_SIZEOF_VOID_P check here would fail the whole configure; the engine
# static_asserts sizeof(void*) == 4 instead, which catches the same mistake at
# the point where it would actually be wrong.
target_compile_options(kp_hooks PUBLIC -m32 -Wall -Wextra)
target_link_options(kp_hooks PUBLIC -m32)

# --- kp_hooktool -------------------------------------------------------------
#
# The harness detours functions inside its own process, so it only builds where
# it can also RUN: native 32-bit Linux. Cross-compiled to Windows it would be a
# binary nobody executes, which is worse than not building it.
if(UNIX AND NOT WIN32)
    add_executable(kp_hooktool
        "${KP_TOOLS_DIR}/kp_hooktool.cpp"
        "${KP_SRC_DIR}/api/memory.cpp")
    target_include_directories(kp_hooktool PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src")
    target_link_libraries(kp_hooktool PRIVATE kp_hooks kp_image
                          "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    target_link_options(kp_hooktool PRIVATE -no-pie)
    # -fcf-protection=none keeps the harness's own prologues predictable, so a
    # test that asserts on decoded lengths is testing the decoder rather than
    # this month's codegen defaults.
    target_compile_options(kp_hooktool PRIVATE -fcf-protection=none)

    # `selftest` exits on its own g_failures counter; `lendis` is a manual
    # decode-and-print subcommand, not a test.
    add_test(NAME kp_hooktool.selftest COMMAND kp_hooktool selftest)

    # hookmanifest/v1 masked-pattern resolution. `selftest` is synthetic;
    # `image <swkotor.exe> <manifest>` is the manual real-image check.
    add_executable(kp_manifesttest
        "${KP_TOOLS_DIR}/kp_manifesttest.cpp"
        "${KP_SRC_DIR}/api/memory.cpp")
    target_include_directories(kp_manifesttest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src")
    target_link_libraries(kp_manifesttest PRIVATE kp_hooks kp_image
                          "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_test(NAME kp_manifesttest.selftest COMMAND kp_manifesttest selftest)

    add_executable(kp_luahooktest
        "${KP_TOOLS_DIR}/kp_luahooktest.cpp"
        "${KP_HOOKS_DIR}/lua_stub.cpp"
        "${KP_HOOKS_DIR}/lua_bridge.cpp"
        "${KP_SRC_DIR}/api/memory.cpp")
    target_include_directories(kp_luahooktest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src")
    target_link_libraries(kp_luahooktest PRIVATE kp_hooks kp_image
                          "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    target_compile_options(kp_luahooktest PRIVATE -fcf-protection=none -fno-pie)
    target_link_options(kp_luahooktest PRIVATE -no-pie)
    add_test(NAME kp_luahooktest COMMAND kp_luahooktest)
endif()

# --- x86_64 detour engine --------------------------------------------------
#
# The 64-bit engine for the Mac x86_64 slice (src/hooks/x64/). It is a
# separate target on purpose: kp_hooks carries PUBLIC -m32 and trampoline.hpp
# static_asserts a 4-byte pointer, and neither may leak in here. Proven
# natively on an x86_64 Linux host only; no Darwin build exists yet.
if(UNIX AND NOT WIN32 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    add_library(kp_hooks_x64 STATIC
        "${KP_HOOKS_DIR}/x64/decode.cpp"
        "${KP_HOOKS_DIR}/x64/trampoline.cpp")
    target_include_directories(kp_hooks_x64 PUBLIC "${KP_SRC_DIR}")
    target_compile_options(kp_hooks_x64 PRIVATE -Wall -Wextra)

    add_executable(kp_hooktool_x64 "${KP_TOOLS_DIR}/kp_hooktool_x64.cpp")
    target_link_libraries(kp_hooktool_x64 PRIVATE kp_hooks_x64)
    target_compile_options(kp_hooktool_x64 PRIVATE -Wall -Wextra)
    add_test(NAME kp_hooktool_x64.selftest COMMAND kp_hooktool_x64 selftest)
endif()

# --- the Windows half --------------------------------------------------------
#
# Compiled, not linked: the runtime DLL that will consume these objects does not
# exist yet, but the point is to catch a Windows-only compile break in the same
# configure that builds the Linux half. Mirrors the image_win32 target so both
# modules are proven by one `cmake --build`.
find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
if(KP_MINGW_CXX)
    set(KP_HOOKS_WIN32_SOURCES
        "${KP_HOOKS_DIR}/trampoline.cpp"
        "${KP_HOOKS_DIR}/registry.cpp"
        "${KP_PLATFORM_DIR}/platform.cpp"
        "${KP_PLATFORM_DIR}/platform_win32.cpp"
    )
    set(KP_HOOKS_WIN32_OBJDIR "${CMAKE_BINARY_DIR}/win32")
    set(KP_HOOKS_WIN32_OBJECTS)
    file(GLOB KP_GENERATED_HEADERS "${KP_SRC_DIR}/generated/*.inc")
    foreach(src ${KP_HOOKS_WIN32_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        set(obj "${KP_HOOKS_WIN32_OBJDIR}/hooks_${name}.obj")
        set(dep "${KP_HOOKS_WIN32_OBJDIR}/hooks_${name}.d")
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_HOOKS_WIN32_OBJDIR}
            COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                    ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2 -I${KP_SRC_DIR}
                    -ffile-prefix-map=${CMAKE_SOURCE_DIR}=.
                    -MD -MF ${dep}
                    -c ${src} -o ${obj}
            DEPENDS ${src} ${KP_GENERATED_HEADERS}
            DEPFILE ${dep}
            COMMENT "i686-w64-mingw32-g++ ${name}.cpp"
            VERBATIM)
        list(APPEND KP_HOOKS_WIN32_OBJECTS ${obj})
    endforeach()
    add_custom_target(hooks_win32 ALL DEPENDS ${KP_HOOKS_WIN32_OBJECTS})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: the hook engine's Windows half is not being compiled")
endif()
