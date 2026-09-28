# Build rules for the headless harness control plane.
#
# An include() fragment in the house style of src/hooks/hooks.cmake. It does
# two things and nothing else: it publishes KP_HARNESS_SOURCES, which
# src/runtime/runtime.cmake appends to kphasor.dll and libkphasor.so, and it
# defines kp_harnesstest, the offline proof of the channel, the codec and the
# ring. It must be included BEFORE runtime.cmake so the source list is set
# when that fragment reads it.
#
# Object names in the flat win32/ directory are rt_<basename>.obj, so every
# basename here has to be unique across runtime/, lua/, events/ and api/ as
# well: channel, commands, json, ring, engine_k1, engine_k2.

set(KP_HARNESS_DIR      "${CMAKE_CURRENT_LIST_DIR}")
set(KP_HARNESS_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_HARNESS_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")

set(KP_HARNESS_SOURCES
    "${KP_HARNESS_DIR}/channel.cpp"
    "${KP_HARNESS_DIR}/commands.cpp"
    "${KP_HARNESS_DIR}/console_protocol.cpp"
    "${KP_HARNESS_DIR}/json.cpp"
    "${KP_HARNESS_DIR}/ring.cpp"
    "${KP_HARNESS_DIR}/engine_k1.cpp"
    "${KP_HARNESS_DIR}/engine_k2.cpp"
)
# The adapters land from a separate packet. Skipping a missing one keeps the
# configure honest about what it found; the DLL link then reports the
# unresolved make_adapter, which is the right place to learn it is absent.
foreach(f ${KP_HARNESS_SOURCES})
    if(NOT EXISTS ${f})
        list(REMOVE_ITEM KP_HARNESS_SOURCES ${f})
        message(STATUS "kphasor: ${f} not present yet, skipping")
    endif()
endforeach()

# --- kp_harnesstest ----------------------------------------------------------
#
# Links channel, json and ring plus the platform layer, with the executor as
# a callback: no runtime, no Lua, no generated tables. It proves that
# requests execute on the thread that drains, that a malformed line gets an
# error reply and keeps the connection, that a second client is refused, that
# the ring keeps order under wrap-around, and that the codec round-trips every
# value type the protocol uses.
#
# Native only: it opens a loopback socket in its own process, and a
# cross-compiled binary nobody runs proves nothing.
if(UNIX AND NOT WIN32)
    find_package(Threads REQUIRED)
    add_executable(kp_harnesstest
        "${KP_HARNESS_TOOLS}/kp_harnesstest.cpp"
        "${KP_HARNESS_DIR}/channel.cpp"
        "${KP_HARNESS_DIR}/json.cpp"
        "${KP_HARNESS_DIR}/ring.cpp"
        "${KP_HARNESS_SRC_ROOT}/platform/platform.cpp"
        "${KP_HARNESS_SRC_ROOT}/platform/platform_linux.cpp"
    )
    target_include_directories(kp_harnesstest PRIVATE "${KP_HARNESS_SRC_ROOT}")
    target_compile_options(kp_harnesstest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_harnesstest PRIVATE -m32)
    target_link_libraries(kp_harnesstest PRIVATE Threads::Threads)

    # Self-contained: exits on its own g_failures counter.
    add_test(NAME kp_harnesstest COMMAND kp_harnesstest)
endif()
