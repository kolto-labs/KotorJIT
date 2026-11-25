# Build rule for the binkw32 proxy.
#
# An include() fragment in the house style of src/hooks/hooks.cmake: paths come
# from CMAKE_CURRENT_LIST_DIR so this works from whichever CMakeLists pulls it
# in.
#
# The proxy is a Windows-only artifact and is always cross-compiled. There is no
# Linux equivalent, because the Linux target is reached with LD_PRELOAD and
# needs no import to hijack.

set(KP_PROXY_DIR "${CMAKE_CURRENT_LIST_DIR}")

if(NOT KP_MINGW_CXX)
    find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
endif()

if(KP_MINGW_CXX)
    set(KP_BINKW32 "${CMAKE_BINARY_DIR}/binkw32.dll")

    # The .def is passed straight to the linker. Every export in it is a
    # forwarder to binkw32_real, so the DLL carries no thunk code and there is
    # nothing to keep in sync when the export list changes.
    #
    # -static and friends because a DLL that drags in libgcc_s_dw2-1.dll or
    # libstdc++-6.dll fails to load under Wine with no diagnostic at all: the
    # loader just does not find them next to the game, and the game starts
    # without the mod for reasons nothing reports.
    add_custom_command(
        OUTPUT ${KP_BINKW32}
        COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2 -shared
                -ffile-prefix-map=${CMAKE_SOURCE_DIR}=.
                -o ${KP_BINKW32}
                "${KP_PROXY_DIR}/binkw32.cpp" "${KP_PROXY_DIR}/binkw32.def"
                -static -static-libgcc -static-libstdc++
                -Wl,--enable-stdcall-fixup
        DEPENDS "${KP_PROXY_DIR}/binkw32.cpp" "${KP_PROXY_DIR}/binkw32.def"
        COMMENT "i686-w64-mingw32-g++ binkw32.dll (proxy)"
        VERBATIM)

    add_custom_target(binkw32 ALL DEPENDS ${KP_BINKW32})
else()
    message(WARNING "i686-w64-mingw32-g++ not found: binkw32.dll is not being built")
endif()
