# Build rules for the runtime and the two shipping libraries it becomes.
#
# An include() fragment in the house style of src/hooks/hooks.cmake.
#
#   kphasor.dll     Windows, 32-bit, everything statically linked
#   libkphasor.so   Linux, 32-bit, the same runtime for the TSL ELF
#
# Both carry image/, hooks/, lua/ and LuaJIT inside them. Nothing is shipped
# alongside: a player drops two files next to the game, and a missing runtime
# DLL is a failure mode with no diagnostic under Wine.

set(KP_RUNTIME_DIR "${CMAKE_CURRENT_LIST_DIR}")
set(KP_SRC_ROOT    "${CMAKE_CURRENT_LIST_DIR}/..")

set(KP_RUNTIME_SOURCES
    "${KP_RUNTIME_DIR}/runtime.cpp"
    "${KP_RUNTIME_DIR}/dllmain.cpp"
    "${KP_RUNTIME_DIR}/fault_guard.cpp"
    "${KP_RUNTIME_DIR}/hook_bodies.cpp"
)

# The Lua host is not a target yet, so its two files are compiled here rather
# than linked from somewhere. They belong to lua/, not to this fragment; when
# they grow a target of their own, this list becomes a target_link_libraries.
set(KP_LUA_SOURCES
    "${KP_SRC_ROOT}/lua/host.cpp"
    "${KP_SRC_ROOT}/lua/value.cpp"
)

set(KP_LUAJIT_WIN_DIR "${CMAKE_SOURCE_DIR}/third_party/luajit/src")

# --- kphasor.dll -------------------------------------------------------------

if(NOT KP_MINGW_CXX)
    find_program(KP_MINGW_CXX i686-w64-mingw32-g++)
endif()

if(KP_MINGW_CXX AND EXISTS "${KP_LUAJIT_WIN_DIR}/libluajit.a")
    set(KP_RT_WIN32_OBJDIR "${CMAKE_BINARY_DIR}/win32")
    set(KP_RT_WIN32_OBJECTS)

    # Generated headers are #included, not compiled, so a hand-written
    # add_custom_command sees no dependency on them and happily reuses a stale
    # object. That is not theoretical: a regenerated event table left the DLL
    # five minutes older than the table it was supposed to contain, and the
    # runtime reported two events as missing from a file that plainly had them.
    # Listing them explicitly is the only thing that makes this correct.
    file(GLOB KP_GENERATED_HEADERS "${KP_SRC_ROOT}/generated/*.inc")

    foreach(src ${KP_RUNTIME_SOURCES} ${KP_LUA_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        set(obj "${KP_RT_WIN32_OBJDIR}/rt_${name}.obj")
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_RT_WIN32_OBJDIR}
            COMMAND ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
                    -I${KP_SRC_ROOT} -I${KP_LUAJIT_WIN_DIR}
                    -c ${src} -o ${obj}
            DEPENDS ${src} ${KP_GENERATED_HEADERS}
            COMMENT "i686-w64-mingw32-g++ ${name}.cpp"
            VERBATIM)
        list(APPEND KP_RT_WIN32_OBJECTS ${obj})
    endforeach()

    # image_win32 and hooks_win32 already compile their halves for Windows.
    # Reusing their objects is what keeps one definition of how those modules
    # are built; recompiling them here would let the two drift.
    set(KP_KPHASOR_DLL "${CMAKE_BINARY_DIR}/kphasor.dll")
    add_custom_command(
        OUTPUT ${KP_KPHASOR_DLL}
        COMMAND ${KP_MINGW_CXX} -shared -o ${KP_KPHASOR_DLL}
                ${KP_RT_WIN32_OBJECTS} ${KP_WIN32_OBJECTS} ${KP_HOOKS_WIN32_OBJECTS}
                "${KP_LUAJIT_WIN_DIR}/libluajit.a"
                # Static, and this is not a preference. A dynamic dependency on
                # libwinpthread-1.dll, libgcc_s_dw2-1.dll or libstdc++-6.dll
                # makes the DLL fail to load under Wine and reports nothing:
                # the game simply starts without the mod.
                -static -static-libgcc -static-libstdc++
                # Nothing outside the process calls into us -- the proxy only
                # needs the DLL to load, and DllMain does the rest. An empty
                # export table says so.
                -Wl,--exclude-all-symbols
        DEPENDS ${KP_RT_WIN32_OBJECTS} image_win32 hooks_win32
                "${KP_LUAJIT_WIN_DIR}/libluajit.a"
        COMMENT "i686-w64-mingw32-g++ kphasor.dll"
        VERBATIM)

    add_custom_target(kphasor_dll ALL DEPENDS ${KP_KPHASOR_DLL})
elseif(NOT KP_MINGW_CXX)
    message(WARNING "i686-w64-mingw32-g++ not found: kphasor.dll is not being built")
else()
    message(WARNING "third_party/luajit/src/libluajit.a (Windows) not found: "
                    "kphasor.dll is not being built")
endif()

# --- libkphasor.so -----------------------------------------------------------
#
# LuaJIT is built into the build tree rather than in third_party, because
# third_party already holds the Windows libluajit.a and an in-tree native build
# would overwrite it with an ELF archive of the same name.

if(UNIX AND NOT WIN32)
    set(KP_LUAJIT_LINUX_DIR "${CMAKE_BINARY_DIR}/luajit32")
    set(KP_LUAJIT_LINUX_LIB "${KP_LUAJIT_LINUX_DIR}/src/libluajit.a")

    add_custom_command(
        OUTPUT ${KP_LUAJIT_LINUX_LIB}
        COMMAND ${CMAKE_COMMAND} -E rm -rf ${KP_LUAJIT_LINUX_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                "${CMAKE_SOURCE_DIR}/third_party/luajit" ${KP_LUAJIT_LINUX_DIR}
        # The copy brings the Windows objects and libluajit.a along with the
        # sources. Building over them fails at the `ar` step, because appending
        # ELF objects to an archive of PE-COFF objects is not a thing.
        COMMAND ${CMAKE_COMMAND} -E chdir ${KP_LUAJIT_LINUX_DIR} make -s clean
        # -fPIC because this ends up inside a shared object. Host and target
        # pointer size must match for LuaJIT's build-time code generator, hence
        # -m32 on HOST_CC as well.
        COMMAND ${CMAKE_COMMAND} -E chdir ${KP_LUAJIT_LINUX_DIR}
                make -s "CC=gcc -m32 -fPIC" "HOST_CC=gcc -m32"
                     BUILDMODE=static TARGET_SYS=Linux
        COMMENT "building LuaJIT for native 32-bit Linux"
        VERBATIM)

    # image/ and hooks/ are compiled again here rather than linked from
    # libkp_image.a and libkp_hooks.a, because those are built without -fPIC:
    # linking them into a shared object produces DT_TEXTREL, which makes the
    # code pages writable and which SELinux can refuse outright. Taking the
    # source lists off the existing targets keeps one definition of what those
    # modules contain -- this fragment never repeats a filename.
    get_target_property(KP_IMAGE_SRC kp_image SOURCES)
    get_target_property(KP_HOOKS_SRC kp_hooks SOURCES)

    add_library(kphasor SHARED ${KP_RUNTIME_SOURCES} ${KP_LUA_SOURCES}
                               ${KP_IMAGE_SRC} ${KP_HOOKS_SRC}
                               ${KP_LUAJIT_LINUX_LIB})
    set_target_properties(kphasor PROPERTIES POSITION_INDEPENDENT_CODE ON)
    target_include_directories(kphasor PRIVATE "${KP_SRC_ROOT}"
                                               "${KP_LUAJIT_LINUX_DIR}/src")
    target_compile_options(kphasor PRIVATE -m32 -Wall -Wextra)
    target_link_options(kphasor PRIVATE -m32)
    # LuaJIT's own two dependencies on Linux. Nothing else we link pulls them
    # in, and the failure without them is a pile of undefined symbols at link.
    target_link_libraries(kphasor PRIVATE ${KP_LUAJIT_LINUX_LIB} m dl)
endif()
