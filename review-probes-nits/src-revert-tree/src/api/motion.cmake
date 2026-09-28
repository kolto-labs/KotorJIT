# kp.motion checked core and Lua surface (K1 GOG only): M1 capture, M2
# relocate / restore / observe, plus the shared engine-thread gate
# (api/engine_gate.cpp). Production sources ship in runtime.cmake:
# motion.cpp motion_profiles.cpp motion_backend.cpp motion_lua.cpp engine_gate.cpp.
if(UNIX AND NOT WIN32)
    add_executable(kp_motiontest "${CMAKE_SOURCE_DIR}/tools/kp_motiontest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/motion.cpp" "${CMAKE_CURRENT_LIST_DIR}/motion_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/motion_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/motion_lua.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/engine_gate.cpp")
    target_include_directories(kp_motiontest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_motiontest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_motiontest PRIVATE -m32)
    target_link_libraries(kp_motiontest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_motiontest kphasor)
    # The argument is the source root: the test cross-checks the generated
    # data/addresses/k1_gog_103.json and data/routines/*.json read-only.
    add_test(NAME kp_motiontest COMMAND kp_motiontest "${CMAKE_SOURCE_DIR}")
    set_tests_properties(kp_motiontest PROPERTIES LABELS "offline;motion")

    # The engine-thread gate on its own, including a real second thread.
    add_executable(kp_enginegatetest "${CMAKE_SOURCE_DIR}/tools/kp_enginegatetest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/engine_gate.cpp")
    target_include_directories(kp_enginegatetest PRIVATE "${CMAKE_SOURCE_DIR}/src")
    target_compile_options(kp_enginegatetest PRIVATE -m32 -Wall -Wextra -pthread)
    target_link_options(kp_enginegatetest PRIVATE -m32 -pthread)
    add_test(NAME kp_enginegatetest COMMAND kp_enginegatetest)
    set_tests_properties(kp_enginegatetest PROPERTIES LABELS "offline;motion")
endif()
