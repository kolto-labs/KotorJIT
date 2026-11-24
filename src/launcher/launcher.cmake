# Build rule for the Windows 32-bit runtime-injection launcher.
#
# Cross-compiled from Linux with i686-w64-mingw32-g++ alongside scriptforge.dll
# and binkw32.dll. Launches native Windows games via CreateProcess(CREATE_SUSPENDED)
# + remote LoadLibraryA, or delayed Steam/attach injection for packed SteamStub builds.

set(KP_LAUNCHER_DIR "${CMAKE_CURRENT_LIST_DIR}")

if(NOT KP_MINGW_CXX)
    find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
endif()

if(KP_MINGW_CXX AND TARGET image_win32)
    set(KP_LAUNCHER_EXE "${CMAKE_BINARY_DIR}/scriptforge-launch.exe")
    set(KP_LAUNCHER_SHA256_OBJ "${KP_WIN32_OBJDIR}/sha256.obj")

    add_custom_command(
        OUTPUT ${KP_LAUNCHER_EXE}
        COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
                "-I${CMAKE_SOURCE_DIR}/src"
                -o ${KP_LAUNCHER_EXE}
                "${KP_LAUNCHER_DIR}/launcher.cpp"
                "${KP_LAUNCHER_SHA256_OBJ}"
                -static -static-libgcc -static-libstdc++ -lshell32
        DEPENDS
            "${KP_LAUNCHER_DIR}/launcher.cpp"
            "${CMAKE_SOURCE_DIR}/src/platform/naming.hpp"
            "${CMAKE_SOURCE_DIR}/src/image/sha256.hpp"
            "${KP_LAUNCHER_SHA256_OBJ}"
            image_win32
        COMMENT "i686-w64-mingw32-g++ scriptforge-launch.exe (injector launcher)"
        VERBATIM)

    add_custom_target(scriptforge_launcher ALL DEPENDS ${KP_LAUNCHER_EXE})
elseif(NOT KP_MINGW_CXX)
    message(WARNING "i686-w64-mingw32-g++ not found: scriptforge-launch.exe is not being built")
endif()
