# Build rules for the pause-lease state machine and its offline test.
#
# An include() fragment in the house style of harness.cmake. It publishes
# KP_PAUSE_LEASE_SOURCES (for the runtime to append once the hooks are wired)
# and defines kp_pause_lease_test, the offline proof of the state machine.
# The unit is engine-independent: no runtime, no Lua, no platform layer.
#
# Object basename pause_lease is unique across runtime/, lua/, events/, api/.

set(KP_PAUSE_LEASE_DIR   "${CMAKE_CURRENT_LIST_DIR}")
set(KP_PAUSE_LEASE_ROOT  "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_PAUSE_LEASE_TOOLS "${CMAKE_CURRENT_LIST_DIR}/../../tools")

set(KP_PAUSE_LEASE_SOURCES "${KP_PAUSE_LEASE_DIR}/pause_lease.cpp")

# Native only, 32-bit like kp_harnesstest: the detours it will sit behind
# are i386 thiscall.
if(UNIX AND NOT WIN32)
    add_executable(kp_pause_lease_test
        "${KP_PAUSE_LEASE_TOOLS}/kp_pause_lease_test.cpp"
        "${KP_PAUSE_LEASE_DIR}/pause_lease.cpp"
    )
    target_include_directories(kp_pause_lease_test PRIVATE "${KP_PAUSE_LEASE_ROOT}")
    target_compile_options(kp_pause_lease_test PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_pause_lease_test PRIVATE -m32)

    # Self-contained: exits on its own g_failures counter.
    add_test(NAME kp_pause_lease_test COMMAND kp_pause_lease_test)
endif()
