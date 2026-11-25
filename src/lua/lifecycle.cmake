# kp_lifecycletest and kp_scriptsapitest -- script load, unload, reload and the
# kp.scripts surface, against the real lua::Host, without the game.
#
# Included from luahost.cmake inside its `TARGET kotorjit` guard, so the native
# 32-bit LuaJIT (KP_LUATEST_LUAJIT) that runtime.cmake builds is available.
# Sources rather than a link against the runtime libraries, for the reason
# support.cmake gives: those are built without -fPIC.
#
# Both tools write their scratch scripts under the build tree's test-tmp dir and
# exit non-zero on any failed case; the exit code is the verdict.

set(KP_LIFECYCLE_SRC "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_LIFECYCLE_TOOLS "${CMAKE_CURRENT_LIST_DIR}/../../tools")
set(KP_LIFECYCLE_COMMON
    "${KP_LIFECYCLE_SRC}/lua/host.cpp"
    "${KP_LIFECYCLE_SRC}/lua/value.cpp"
    "${KP_LIFECYCLE_SRC}/api/output.cpp"
    "${KP_LIFECYCLE_SRC}/api/timers.cpp"
    "${KP_LIFECYCLE_SRC}/api/strings.cpp"
    "${KP_LIFECYCLE_SRC}/platform/platform.cpp"
    "${KP_LIFECYCLE_SRC}/platform/platform_linux.cpp"
)
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/test-tmp")

foreach(kp_lifecycle_tool kp_lifecycletest kp_scriptsapitest)
    set(kp_lifecycle_extra "")
    if(kp_lifecycle_tool STREQUAL "kp_scriptsapitest")
        set(kp_lifecycle_extra "${KP_LIFECYCLE_SRC}/api/scripts_lua.cpp")
    endif()
    add_executable(${kp_lifecycle_tool}
        "${KP_LIFECYCLE_TOOLS}/${kp_lifecycle_tool}.cpp"
        ${kp_lifecycle_extra}
        ${KP_LIFECYCLE_COMMON}
    )
    target_include_directories(${kp_lifecycle_tool} PRIVATE
        "${KP_LIFECYCLE_SRC}" "${CMAKE_BINARY_DIR}/luajit32/src")
    target_compile_options(${kp_lifecycle_tool} PRIVATE -m32 -Wall -Wextra)
    target_link_options(${kp_lifecycle_tool} PRIVATE -m32)
    target_compile_definitions(${kp_lifecycle_tool} PRIVATE KP_REPO="${CMAKE_SOURCE_DIR}")
    add_dependencies(${kp_lifecycle_tool} kotorjit)
    target_link_libraries(${kp_lifecycle_tool} PRIVATE "${KP_LUATEST_LUAJIT}" m dl)
    add_test(NAME ${kp_lifecycle_tool}
             COMMAND ${kp_lifecycle_tool} "${CMAKE_BINARY_DIR}/test-tmp/${kp_lifecycle_tool}")
    set_tests_properties(${kp_lifecycle_tool} PROPERTIES
        LABELS "offline;lifecycle"
        ENVIRONMENT "TMPDIR=${CMAKE_BINARY_DIR}/test-tmp")
endforeach()
