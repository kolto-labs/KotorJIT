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
elseif(UNIX AND NOT WIN32)
    message(STATUS "kp_luatest needs the native LuaJIT that the kphasor target "
                   "builds; include src/runtime/runtime.cmake first")
endif()
