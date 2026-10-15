# Build rules for the memory-module offline harness.
#
# memory.cpp already ships inside kphasor (runtime.cmake's KP_API_SOURCES).
# This fragment only builds kp_memtest, which is Linux/32-bit and -no-pie:
# it probes its own process through kp.mem and src/image reads ELF
# program headers out of the live mapping. Include after runtime.cmake so
# add_dependencies(kphasor) names a target that already exists; the LuaJIT
# archive itself is a build-time output, same as the other harnesses.

set(KP_MEMORY_DIR      "${CMAKE_CURRENT_LIST_DIR}")
set(KP_MEMORY_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_MEMORY_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")
set(KP_LUAJIT_NATIVE_DIR "${CMAKE_BINARY_DIR}/luajit32/src")

if(UNIX AND NOT WIN32)
    set(KP_LUAJIT_NATIVE_LIB "${KP_LUAJIT_NATIVE_DIR}/libluajit.a")
    add_executable(kp_memtest
        "${KP_MEMORY_TOOLS}/kp_memtest.cpp"
        "${KP_MEMORY_DIR}/memory.cpp")
    target_include_directories(kp_memtest PRIVATE
        "${KP_MEMORY_SRC_ROOT}"
        "${KP_LUAJIT_NATIVE_DIR}")
    target_link_libraries(kp_memtest PRIVATE kp_image kp_hooks
                          "${KP_LUAJIT_NATIVE_LIB}" m dl)
    target_link_options(kp_memtest PRIVATE -no-pie)
    add_dependencies(kp_memtest kphasor)

    # Self-contained: exits 0 when Lua checks plus C++ byte comparisons are 0.
    add_test(NAME kp_memtest COMMAND kp_memtest)

    if(TARGET kp_hooktool)
        add_dependencies(kp_hooktool kphasor)
    endif()
    if(TARGET kp_manifesttest)
        add_dependencies(kp_manifesttest kphasor)
    endif()
endif()
