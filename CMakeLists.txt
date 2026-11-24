# Hyperstim build.
#
# Both game targets are 32-bit: KOTOR 1 is a PE32 for i386, KOTOR 2 on Linux is
# an ELF32 EXEC. Nothing here is ever built 64-bit, and the Windows half is
# cross-compiled from this machine rather than built on Windows.
#
#   cmake -S . -B build && cmake --build build      native tools, g++ -m32
#   cmake --build build --target image_win32        Windows cross-compile check
cmake_minimum_required(VERSION 3.20)
project(Hyperstim VERSION 0.1.0 LANGUAGES CXX)

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

# macOS is built by scripts/mac/build.sh, not by this CMake tree. The rest of
# this file assumes a 32-bit-capable GCC/Clang and the mingw cross toolchain
# (the Windows and Linux game ABIs are i386); an Apple host has neither, and
# forcing a -m32 configure there fails before anything useful happens. So on
# APPLE this file configures a single convenience target that shells out to the
# build script, and stops. The macOS runtime, its address tables and its
# offline verification live under scripts/mac/ and tools/mac/.
if(APPLE)
    add_custom_target(hyperstim_mac ALL
        COMMAND ${CMAKE_COMMAND} -E env bash ${CMAKE_SOURCE_DIR}/scripts/mac/build.sh
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        COMMENT "Building libhyperstim.dylib via scripts/mac/build.sh (x86_64)"
        VERBATIM USES_TERMINAL)
    find_package(Python3 3.9 COMPONENTS Interpreter)
    if(Python3_FOUND)
        add_test(NAME mac_tables_test
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/mac/mac_tables_test.py)
        set_tests_properties(mac_tables_test PROPERTIES LABELS "offline;mac" TIMEOUT 60)
    endif()
    # The x86_64 detour engine's self-test builds and runs on any x86_64 host,
    # macOS included; it is the same binary the Linux CI runs.
    add_executable(kp_hooktool_x64 tools/kp_hooktool_x64.cpp
        src/hooks/x64/decode.cpp src/hooks/x64/trampoline.cpp)
    target_include_directories(kp_hooktool_x64 PRIVATE src)
    target_compile_options(kp_hooktool_x64 PRIVATE -Wall -Wextra)
    add_test(NAME kp_hooktool_x64.selftest COMMAND kp_hooktool_x64 selftest)
    add_dependencies(hyperstim_mac kp_hooktool_x64)
    # The x86_64 engine-ABI unit test (layout widths, id truncation, the
    # ExecuteCommand bound decoders). Runs on any x86_64 host.
    add_executable(kp_mac_abitest tools/mac/kp_mac_abitest.cpp)
    target_include_directories(kp_mac_abitest PRIVATE src)
    target_compile_options(kp_mac_abitest PRIVATE -Wall -Wextra)
    add_test(NAME kp_mac_abitest COMMAND kp_mac_abitest)
    add_dependencies(hyperstim_mac kp_mac_abitest)
    message(STATUS "macOS host: `cmake --build` runs scripts/mac/build.sh; "
                   "`ctest` runs the Mach-O table gate and the x86_64 detour self-test; "
                   "run tools/mac/gen_mac_tables.py --check against the local images for full byte verification.")
    return()
endif()

# These are offline fake-server/parser gates; no game, Wine or display is launched.
find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
foreach(gate kpharness_offline_test kpharness_world_test kpharness_creative_test kpharness_physical_console_test kpharness_gamescope_backend_test)
    add_test(NAME ${gate} COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/${gate}.py)
    set_tests_properties(${gate} PROPERTIES LABELS "offline;harness" TIMEOUT 300)
endforeach()
add_test(NAME gameplay_scheduler_test
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/gameplay_scheduler_test.sh)
set_tests_properties(gameplay_scheduler_test PROPERTIES LABELS "offline;harness" TIMEOUT 60)

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
    src/image/macho.cpp
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

# SDK-independent metadata parser test, also buildable on a 64-bit host.
add_executable(kp_machotest tools/kp_machotest.cpp src/image/macho.cpp)
target_include_directories(kp_machotest PRIVATE src)
target_compile_options(kp_machotest PRIVATE -Wall -Wextra)
add_test(NAME kp_machotest COMMAND kp_machotest)
add_test(NAME kp_imagetool_macho_test
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/kp_imagetool_macho_test.py $<TARGET_FILE:kp_imagetool>)

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

# The runtime, and the two libraries it ships as: hyperstim.dll and libhyperstim.so.
# After hooks.cmake because it links what image_win32 and hooks_win32 compile.
# Host API libraries and source lists, in their established dependency order.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/api.cmake)

# The headless harness control plane. Before runtime.cmake: it only publishes
# KP_HARNESS_SOURCES for that fragment to compile into both libraries, and
# defines kp_harnesstest, which needs no runtime.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/harness/harness.cmake)

include(${CMAKE_CURRENT_SOURCE_DIR}/src/runtime/runtime.cmake)

# After runtime.cmake: kp_memtest links the native LuaJIT that target builds.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/api_luajit.cmake)

# The Lua host on its own, for exercising the arbitration rule without the game.
# After runtime.cmake: it links the native LuaJIT that target builds.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/lua/luahost.cmake)

# Exact inventory, Lua behavior, real-host arbitration and multiplayer mocks.
if(TARGET kp_luatest)
    find_program(KP_EXAMPLE_LUAJIT NAMES luajit REQUIRED)
    add_test(NAME example_validation
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/example_validation.py
            --luajit ${KP_EXAMPLE_LUAJIT} --host $<TARGET_FILE:kp_luatest>
            --receipt ${CMAKE_BINARY_DIR}/example-validation.json)
    set_tests_properties(example_validation PROPERTIES LABELS "offline;examples" TIMEOUT 180)
endif()


# The binkw32 proxy: the DLL the game actually imports, which loads the runtime.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/proxy/proxy.cmake)

if(UNIX AND NOT WIN32)
    add_executable(kp_projectilestest tools/kp_projectilestest.cpp src/api/projectiles.cpp
        src/api/projectiles_lua.cpp src/api/projectiles_entry.cpp ${KP_LUAJIT_LINUX_LIB})
    target_include_directories(kp_projectilestest PRIVATE src third_party/luajit/src)
    target_compile_options(kp_projectilestest PRIVATE -m32 -fno-pie -Wall -Wextra)
    target_link_options(kp_projectilestest PRIVATE -m32 -no-pie)
    target_link_libraries(kp_projectilestest PRIVATE ${KP_LUAJIT_LINUX_LIB} m dl Threads::Threads)
    add_test(NAME kp_projectilestest COMMAND kp_projectilestest)
    set_tests_properties(kp_projectilestest PROPERTIES TIMEOUT 10 LABELS "offline;projectiles;abi")

    add_executable(kp_consoleprotocoltest tools/kp_consoleprotocoltest.cpp
        src/harness/console_protocol.cpp src/harness/json.cpp src/devtools/console.cpp ${KP_LUAJIT_LINUX_LIB})
    target_include_directories(kp_consoleprotocoltest PRIVATE src third_party/luajit/src)
    target_compile_options(kp_consoleprotocoltest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_consoleprotocoltest PRIVATE -m32)
    target_link_libraries(kp_consoleprotocoltest PRIVATE ${KP_LUAJIT_LINUX_LIB} m dl Threads::Threads)
    add_test(NAME kp_consoleprotocoltest COMMAND kp_consoleprotocoltest)
    set_tests_properties(kp_consoleprotocoltest PROPERTIES TIMEOUT 10 LABELS "offline;devtools")

    add_executable(kp_consoletest tools/kp_consoletest.cpp src/devtools/console.cpp ${KP_LUAJIT_LINUX_LIB})
    target_include_directories(kp_consoletest PRIVATE src third_party/luajit/src)
    target_compile_options(kp_consoletest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_consoletest PRIVATE -m32)
    target_link_libraries(kp_consoletest PRIVATE ${KP_LUAJIT_LINUX_LIB} m dl Threads::Threads)
    add_test(NAME kp_consoletest COMMAND kp_consoletest)
    set_tests_properties(kp_consoletest PROPERTIES TIMEOUT 10 LABELS "offline;devtools")
endif()

if(UNIX AND NOT WIN32)
    add_executable(kp_editorinputtest tools/kp_editorinputtest.cpp src/devtools/editor_input.cpp
        third_party/imgui/imgui.cpp third_party/imgui/imgui_draw.cpp
        third_party/imgui/imgui_tables.cpp third_party/imgui/imgui_widgets.cpp)
    target_include_directories(kp_editorinputtest PRIVATE src third_party/imgui)
    target_compile_options(kp_editorinputtest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_editorinputtest PRIVATE -m32)
    target_link_libraries(kp_editorinputtest PRIVATE Threads::Threads)
    add_test(NAME kp_editorinputtest COMMAND kp_editorinputtest)
    set_tests_properties(kp_editorinputtest PROPERTIES TIMEOUT 20 LABELS "offline;devtools;imgui")
endif()
