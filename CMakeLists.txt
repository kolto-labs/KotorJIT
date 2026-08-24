# KotorPhasor build.
#
# Both game targets are 32-bit: KOTOR 1 is a PE32 for i386, KOTOR 2 on Linux is
# an ELF32 EXEC. Nothing here is ever built 64-bit, and the Windows half is
# cross-compiled from this machine rather than built on Windows.
#
#   cmake -S . -B build && cmake --build build      native tools, g++ -m32
#   cmake --build build --target image_win32        Windows cross-compile check
cmake_minimum_required(VERSION 3.20)
project(KotorPhasor CXX)

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
            COMMAND ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2 -Isrc
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

include(${CMAKE_CURRENT_SOURCE_DIR}/src/runtime/runtime.cmake)

# The binkw32 proxy: the DLL the game actually imports, which loads the runtime.
include(${CMAKE_CURRENT_SOURCE_DIR}/src/proxy/proxy.cmake)
