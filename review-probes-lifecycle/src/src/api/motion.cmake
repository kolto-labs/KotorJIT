# kp.motion Stage M1 checked core and Lua surface (read-only, K1 GOG only);
# production sources ship in runtime.cmake.
if(UNIX AND NOT WIN32)
    add_executable(kp_motiontest "${CMAKE_SOURCE_DIR}/tools/kp_motiontest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/motion.cpp" "${CMAKE_CURRENT_LIST_DIR}/motion_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/motion_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/motion_lua.cpp")
    target_include_directories(kp_motiontest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_motiontest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_motiontest PRIVATE -m32)
    target_link_libraries(kp_motiontest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_motiontest kphasor)
    # The argument is the source root: the test cross-checks the generated
    # data/addresses/k1_gog_103.json read-only.
    add_test(NAME kp_motiontest COMMAND kp_motiontest "${CMAKE_SOURCE_DIR}")
    set_tests_properties(kp_motiontest PROPERTIES LABELS "offline;motion")
endif()
