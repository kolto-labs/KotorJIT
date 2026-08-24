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
    add_executable(kp_hooktool "${KP_TOOLS_DIR}/kp_hooktool.cpp")
    target_link_libraries(kp_hooktool PRIVATE kp_hooks)
    # -fcf-protection=none keeps the harness's own prologues predictable, so a
    # test that asserts on decoded lengths is testing the decoder rather than
    # this month's codegen defaults.
    target_compile_options(kp_hooktool PRIVATE -fcf-protection=none)
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
    foreach(src ${KP_HOOKS_WIN32_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        set(obj "${KP_HOOKS_WIN32_OBJDIR}/hooks_${name}.obj")
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_HOOKS_WIN32_OBJDIR}
            COMMAND ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2 -I${KP_SRC_DIR}
                    -c ${src} -o ${obj}
            DEPENDS ${src}
            COMMENT "i686-w64-mingw32-g++ ${name}.cpp"
            VERBATIM)
        list(APPEND KP_HOOKS_WIN32_OBJECTS ${obj})
    endforeach()
    add_custom_target(hooks_win32 ALL DEPENDS ${KP_HOOKS_WIN32_OBJECTS})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: the hook engine's Windows half is not being compiled")
endif()
