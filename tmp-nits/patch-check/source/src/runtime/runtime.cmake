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

set(KP_DEVTOOLS_WIN_SOURCES
    "${KP_SRC_ROOT}/devtools/editor_input.cpp"
    "${KP_SRC_ROOT}/../third_party/imgui/imgui.cpp"
    "${KP_SRC_ROOT}/../third_party/imgui/imgui_draw.cpp"
    "${KP_SRC_ROOT}/../third_party/imgui/imgui_tables.cpp"
    "${KP_SRC_ROOT}/../third_party/imgui/imgui_widgets.cpp"
    "${KP_SRC_ROOT}/../third_party/imgui/backends/imgui_impl_win32.cpp"
    "${KP_SRC_ROOT}/../third_party/imgui/backends/imgui_impl_opengl2.cpp"
)
set(KP_RUNTIME_SOURCES
    "${KP_RUNTIME_DIR}/runtime.cpp"
    "${KP_SRC_ROOT}/devtools/console.cpp"
    "${KP_SRC_ROOT}/devtools/overlay.cpp"
    "${KP_RUNTIME_DIR}/dllmain.cpp"
    "${KP_RUNTIME_DIR}/fault_guard.cpp"
    "${KP_RUNTIME_DIR}/hook_bodies.cpp"
    "${KP_SRC_ROOT}/multiplayer/transport.cpp"
)

# The Lua host is not a target yet, so its two files are compiled here rather
# than linked from somewhere. They belong to lua/, not to this fragment; when
# they grow a target of their own, this list becomes a target_link_libraries.
set(KP_LUA_SOURCES
    "${KP_SRC_ROOT}/lua/host.cpp"
    "${KP_SRC_ROOT}/lua/value.cpp"
    "${KP_SRC_ROOT}/events/dispatch.cpp"
    "${KP_SRC_ROOT}/events/table.cpp"
    "${KP_SRC_ROOT}/events/payload.cpp"
    "${KP_SRC_ROOT}/events/situation.cpp"
)

# The host API. Compiled in here rather than linked, for the same reason as the
# Lua host: these are what a script actually calls, so they have to live in the
# same binary as the interpreter. Each src/api fragment publishes its own source
# list; this is the one place that decides they all ship together.
set(KP_API_SOURCES
    "${KP_SRC_ROOT}/api/routines.cpp"
    "${KP_SRC_ROOT}/api/enginestruct.cpp"
    "${KP_SRC_ROOT}/api/structs.cpp"
    "${KP_SRC_ROOT}/api/entity.cpp"
    "${KP_SRC_ROOT}/api/memory.cpp"
    "${KP_SRC_ROOT}/api/model.cpp"
    "${KP_SRC_ROOT}/api/model_profiles.cpp"
    "${KP_SRC_ROOT}/api/model_backend.cpp"
    "${KP_SRC_ROOT}/api/model_lua.cpp"
    "${KP_SRC_ROOT}/api/animation.cpp"
    "${KP_SRC_ROOT}/api/animation_profiles.cpp"
    "${KP_SRC_ROOT}/api/animation_backend.cpp"
    "${KP_SRC_ROOT}/api/animation_lua.cpp"
    "${KP_SRC_ROOT}/api/output.cpp"
    "${KP_SRC_ROOT}/api/timers.cpp"
    "${KP_SRC_ROOT}/api/strings.cpp"
    "${KP_SRC_ROOT}/api/compat.cpp"
)
foreach(f ${KP_API_SOURCES})
    if(NOT EXISTS ${f})
        list(REMOVE_ITEM KP_API_SOURCES ${f})
        message(STATUS "kphasor: ${f} not present yet, skipping")
    endif()
endforeach()

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

    # KP_HARNESS_SOURCES comes from src/harness/harness.cmake, included before
    # this fragment; empty when that fragment was not included.
    foreach(src ${KP_DEVTOOLS_WIN_SOURCES} ${KP_RUNTIME_SOURCES} ${KP_LUA_SOURCES} ${KP_API_SOURCES} ${KP_HARNESS_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        set(obj "${KP_RT_WIN32_OBJDIR}/rt_${name}.obj")
        # -MD records the headers this object really depends on and DEPFILE
        # hands that list to the generator. Without it the rule sees only the
        # .cpp and the generated tables, so editing a header rebuilds nothing,
        # the DLL keeps the previous object, and a live run silently exercises
        # the code you thought you had just changed. That happened once here.
        set(dep "${KP_RT_WIN32_OBJDIR}/rt_${name}.d")
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${KP_RT_WIN32_OBJDIR}
            COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                    ${KP_MINGW_CXX} -std=c++20 -Wall -Wextra -O2
                    -I${KP_SRC_ROOT} -I${KP_LUAJIT_WIN_DIR} -I${CMAKE_SOURCE_DIR}/third_party/imgui
                    -MD -MF ${dep}
                    -c ${src} -o ${obj}
            DEPENDS ${src} ${KP_GENERATED_HEADERS}
            DEPFILE ${dep}
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
        COMMAND ${CMAKE_COMMAND} -E env TMPDIR=${KP_COMPILER_TMPDIR}
                ${KP_MINGW_CXX} -shared -o ${KP_KPHASOR_DLL}
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
                # The harness channel's loopback listener. An import library,
                # so -static above does not apply to it; ws2_32.dll is part of
                # every Windows and of Wine.
                -lws2_32 -lopengl32 -lgdi32 -limm32 -ldwmapi -ldinput8 -ldxguid
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

    add_library(kphasor SHARED ${KP_RUNTIME_SOURCES} ${KP_LUA_SOURCES} ${KP_API_SOURCES}
                               ${KP_IMAGE_SRC} ${KP_HOOKS_SRC}
                               ${KP_HARNESS_SOURCES}
                               ${KP_LUAJIT_LINUX_LIB})
    set_target_properties(kphasor PROPERTIES POSITION_INDEPENDENT_CODE ON)
    # Both LuaJIT header paths. The build-time copy is what the archive is built
    # from, but it does not exist until its custom command runs, and object
    # compiles do not all order after that. The pristine source tree has the same
    # headers and is always there, so listing it second removes the race without
    # changing which archive is linked.
    target_include_directories(kphasor PRIVATE "${KP_SRC_ROOT}"
                                               "${KP_LUAJIT_LINUX_DIR}/src"
                                               "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kphasor PRIVATE -m32 -Wall -Wextra)
    target_link_options(kphasor PRIVATE -m32)
    # LuaJIT's own two dependencies on Linux. Nothing else we link pulls them
    # in, and the failure without them is a pile of undefined symbols at link.
    target_link_libraries(kphasor PRIVATE ${KP_LUAJIT_LINUX_LIB} m dl)
    # The harness channel's listener thread. Threads::Threads rather than a
    # bare -lpthread so the 32-bit link gets whatever this glibc needs.
    find_package(Threads REQUIRED)
    target_link_libraries(kphasor PRIVATE Threads::Threads)
endif()
