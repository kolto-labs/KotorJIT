# KotorPhasor build.
#
# Both game targets are 32-bit: KOTOR 1 is a PE32 for i386, KOTOR 2 on Linux is
# an ELF32 EXEC. Nothing here is ever built 64-bit, and the Windows half is
# cross-compiled from this machine rather than built on Windows.
#
#   cmake -S . -B build && cmake --build build      native tools, g++ -m32
#   cmake --build build --target image_win32        Windows cross-compile check
cmake_minimum_required(VERSION 3.20)
project(KotorPhasor VERSION 0.1.0 LANGUAGES CXX)

# Some development hosts enforce a small per-user quota on the shared /tmp.
# GCC writes large intermediate assembly files there even when the object file
# belongs in the build tree, which can make an otherwise healthy build fail
# with "Disk quota exceeded".  Keep compiler scratch data with the build so a
# normal `cmake --build` is self-contained and does not depend on host /tmp.
set(KP_COMPILER_TMPDIR "${CMAKE_BINARY_DIR}/compiler-tmp")
file(MAKE_DIRECTORY "${KP_COMPILER_TMPDIR}")
set_property(GLOBAL PROPERTY RULE_LAUNCH_COMPILE
    "${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}")

# The offline tools under tools/ (kp_luatest, kp_eventtest, kp_structtest,
# kp_entitytest, kp_memtest, kp_supporttest, kp_hooktool) exercise the runtime
# with no game install and no Wine: script fixtures under scripts/examples/,
# generated tables under src/generated/, and self-process probes for memory
# and hooks. `ctest` is the one fast, authoritative, idempotent command;
# scripts/harness/ stays a separate, explicitly opt-in tier that needs a real
# KOTOR install.
enable_testing()

# These are offline fake-server/parser gates; no game, Wine or display is launched.
find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
foreach(gate kpharness_offline_test kpharness_world_test)
    add_test(NAME ${gate} COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/${gate}.py)
    set_tests_properties(${gate} PROPERTIES LABELS "offline;harness" TIMEOUT 300)
endforeach()

# Classification reads every byte of every section, twice over for the marker
# scan. Unoptimised that is a third of a second at load time, inside a game's
# startup, so an optimised default is the honest one.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(KP_IMAGE_SOURCES
    src/image/sha256.cpp
    src/image/loaded_image.cpp
    src/image/pe_elf.cpp
    src/image/parse.cpp
    src/image/classify.cpp
    src/image/build_table.cpp
    src/image/load.cpp
)

add_library(kp_image STATIC ${KP_IMAGE_SOURCES})
target_include_directories(kp_image PUBLIC src)
target_compile_options(kp_image PUBLIC -m32 -Wall -Wextra)
target_link_options(kp_image PUBLIC -m32)

# The offline proof that the module works: classification, identification and
# parsing run against files, so the encrypted build can be checked without Steam.
add_executable(kp_imagetool tools/kp_imagetool.cpp)
target_link_libraries(kp_imagetool PRIVATE kp_image)

find_package(Threads REQUIRED)
add_executable(kp_transporttest tools/kp_transporttest.cpp src/multiplayer/transport.cpp)
target_include_directories(kp_transporttest PRIVATE src)
target_compile_options(kp_transporttest PRIVATE -m32 -Wall -Wextra)
target_link_options(kp_transporttest PRIVATE -m32)
target_link_libraries(kp_transporttest PRIVATE Threads::Threads)
add_test(NAME kp_transporttest COMMAND kp_transporttest)

# The same sources through the Windows cross compiler. A custom target rather
# than a toolchain file so one configure of this tree proves both halves build;
# the runtime DLL that will link this gets a proper toolchain file when it lands.
find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
if(KP_MINGW_CXX)
    set(KP_WIN32_OBJDIR ${CMAKE_BINARY_DIR}/win32)
    set(KP_WIN32_OBJECTS)
    foreach(src ${KP_IMAGE_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        set(obj ${KP_WIN32_OBJDIR}/${name}.obj)
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_WIN32_OBJDIR}
            COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                    ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2 -Isrc
                    -c ${CMAKE_SOURCE_DIR}/${src} -o ${obj}
            DEPENDS ${CMAKE_SOURCE_DIR}/${src}
            WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
            COMMENT "i686-w64-mingw32-g++ ${src}"
            VERBATIM)
        list(APPEND KP_WIN32_OBJECTS ${obj})
    endforeach()
    add_custom_target(image_win32 ALL DEPENDS ${KP_WIN32_OBJECTS})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: the Windows half is not being compiled")
endif()

# Hook engine: trampolines, platform layer, address-table registry.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/hooks/hooks.cmake)

# The runtime, and the two libraries it ships as: kphasor.dll and libkphasor.so.
# After hooks.cmake because it links what image_win32 and hooks_win32 compile.
# Host API modules. Each fragment is self-contained and order-independent.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/routines.cmake)
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/structs.cmake)
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/entity.cmake)
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/support.cmake)

# The headless harness control plane. Before runtime.cmake: it only publishes
# KP_HARNESS_SOURCES for that fragment to compile into both libraries, and
# defines kp_harnesstest, which needs no runtime.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/harness/harness.cmake)

include(${CMAKE_CURRENT_SOURCE_DIR}/src/runtime/runtime.cmake)

# After runtime.cmake: kp_memtest links the native LuaJIT that target builds.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/memory.cmake)

# The Lua host on its own, for exercising the arbitration rule without the game.
# After runtime.cmake: it links the native LuaJIT that target builds.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/lua/luahost.cmake)

# The binkw32 proxy: the DLL the game actually imports, which loads the runtime.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/proxy/proxy.cmake)

if(UNIX AND NOT WIN32)
    add_executable(kp_consoletest tools/kp_consoletest.cpp src/devtools/console.cpp ${KP_LUAJIT_LINUX_LIB})
    target_include_directories(kp_consoletest PRIVATE src third_party/luajit/src)
    target_compile_options(kp_consoletest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_consoletest PRIVATE -m32)
    target_link_libraries(kp_consoletest PRIVATE ${KP_LUAJIT_LINUX_LIB} m dl Threads::Threads)
    add_test(NAME kp_consoletest COMMAND kp_consoletest)
    set_tests_properties(kp_consoletest PROPERTIES TIMEOUT 10 LABELS "offline;devtools")
endif()
