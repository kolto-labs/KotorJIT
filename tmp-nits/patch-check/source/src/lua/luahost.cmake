# kp_luatest -- the Lua host and the arbitration rule, without the game.
#
# The rule that decides which of several disagreeing scripts wins an event is the
# part of the design most easily got subtly wrong, and it is only checkable by
# running scripts that disagree. Wiring it to a real game event first would mean
# debugging the rule and the hook at the same time, so this links the real
# lua::Host and dispatcher against a synthetic event and prints the outcome.
#
#   kp_luatest scripts/examples/arbitration OnRunScript k_def_heartbt01 0 0
#   kp_luatest scripts/examples/showcase --list
#
# Sources rather than a link against the runtime libraries, for the reason
# support.cmake gives: those are built without -fPIC, and compiling the handful
# of files this needs is cheaper than pulling in the hook engine to get them.

set(KP_LUATEST_LUAJIT "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a")

if(UNIX AND NOT WIN32 AND TARGET kphasor)
    add_executable(kp_luatest
        "${CMAKE_SOURCE_DIR}/tools/kp_luatest.cpp"
        "${CMAKE_SOURCE_DIR}/src/lua/host.cpp"
        "${CMAKE_SOURCE_DIR}/src/lua/value.cpp"
        "${CMAKE_SOURCE_DIR}/src/events/dispatch.cpp"
        "${CMAKE_SOURCE_DIR}/src/platform/platform.cpp"
        "${CMAKE_SOURCE_DIR}/src/platform/platform_linux.cpp"
    )
    target_include_directories(kp_luatest PRIVATE
        "${CMAKE_SOURCE_DIR}/src" "${CMAKE_BINARY_DIR}/luajit32/src")
    target_compile_options(kp_luatest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_luatest PRIVATE -m32)
    # The generated event contract is an #include, not a source, so the normal
    # dependency scan does not see it. Without this a regenerated events.inc
    # leaves a binary that disagrees with the table it claims to hold.
    file(GLOB KP_LUATEST_GENERATED "${CMAKE_SOURCE_DIR}/src/generated/*.inc")
    set_source_files_properties("${CMAKE_SOURCE_DIR}/tools/kp_luatest.cpp"
        PROPERTIES OBJECT_DEPENDS "${KP_LUATEST_GENERATED}")
    # runtime.cmake owns the LuaJIT build; this only waits for it.
    add_dependencies(kp_luatest kphasor)
    target_link_libraries(kp_luatest PRIVATE "${KP_LUATEST_LUAJIT}" m dl)

    # kp_luatest is a print-and-inspect tool (it always exits 0 on a valid
    # dispatch), so these assert on its stdout narrative instead of its exit
    # code. Each fixture dir under scripts/examples/ documents its own expected
    # outcome in a header comment; the regex below is that comment made
    # machine-checked.
    add_test(NAME kp_luatest.arbitration
             COMMAND kp_luatest scripts/examples/arbitration OnRunScript k_def_heartbt01 0 0
             WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
    set_tests_properties(kp_luatest.arbitration PROPERTIES
        PASS_REGULAR_EXPRESSION "claimed by  : 25_claims_via_string")

    add_test(NAME kp_luatest.fallback
             COMMAND kp_luatest scripts/examples/edge_fallback OnRunScript k_def_heartbt01 0 0
             WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
    set_tests_properties(kp_luatest.fallback PROPERTIES
        PASS_REGULAR_EXPRESSION "no \\(fallback applied\\)")

    add_test(NAME kp_luatest.quarantine
             COMMAND kp_luatest scripts/examples/edge_quarantine OnTick 0 --repeat 3
             WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
    set_tests_properties(kp_luatest.quarantine PROPERTIES
        PASS_REGULAR_EXPRESSION "quarantined after 3 errors")

    # Host-side proof that EventHandler identity, CScriptEvent reads, and the
    # thiscall cleanup for five stack arguments are correct -- without launching
    # the game. Address tables are loaded as data; nothing is patched in swkotor.
    add_executable(kp_eventtest
        "${CMAKE_SOURCE_DIR}/tools/kp_eventtest.cpp"
        "${CMAKE_SOURCE_DIR}/src/events/table.cpp"
        "${CMAKE_SOURCE_DIR}/src/events/payload.cpp"
        "${CMAKE_SOURCE_DIR}/src/events/situation.cpp"
        "${CMAKE_SOURCE_DIR}/src/events/dispatch.cpp"
        "${CMAKE_SOURCE_DIR}/src/lua/host.cpp"
        "${CMAKE_SOURCE_DIR}/src/lua/value.cpp"
        # registry.cpp's signature fallback calls api::memory::find_unique and
        # kp_hooks does not carry that object; kp_hooktool lists it the same way.
        "${CMAKE_SOURCE_DIR}/src/api/memory.cpp"
    )
    target_include_directories(kp_eventtest PRIVATE
        "${CMAKE_SOURCE_DIR}/src" "${CMAKE_BINARY_DIR}/luajit32/src")
    target_compile_options(kp_eventtest PRIVATE -m32 -Wall -Wextra -fcf-protection=none)
    target_link_options(kp_eventtest PRIVATE -m32)
    target_compile_definitions(kp_eventtest PRIVATE KP_REPO="${CMAKE_SOURCE_DIR}")
    set_source_files_properties("${CMAKE_SOURCE_DIR}/src/events/table.cpp"
        PROPERTIES OBJECT_DEPENDS "${KP_LUATEST_GENERATED}")
    add_dependencies(kp_eventtest kphasor)
    # kp_image: memory.cpp walks the mapped image's sections through it.
    target_link_libraries(kp_eventtest PRIVATE kp_hooks kp_image "${KP_LUATEST_LUAJIT}" m dl)

    # Self-contained: exits 0 on kp_eventtest's own g_failures == 0.
    add_test(NAME kp_eventtest COMMAND kp_eventtest)
    # Keep temporary Lua scripts and situation sidecars off a quota-limited
    # system /tmp; this also makes the test deterministic in constrained CI.
    file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/test-tmp")
    set_tests_properties(kp_eventtest PROPERTIES
        ENVIRONMENT "TMPDIR=${CMAKE_BINARY_DIR}/test-tmp")
elseif(UNIX AND NOT WIN32)
    message(STATUS "kp_luatest needs the native LuaJIT that the kphasor target "
                   "builds; include src/runtime/runtime.cmake first")
endif()
