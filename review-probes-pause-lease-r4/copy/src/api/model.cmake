# Shared checked core and Lua surface; production sources ship in runtime.cmake.
if(UNIX AND NOT WIN32)
    add_executable(kp_modeltest "${CMAKE_SOURCE_DIR}/tools/kp_modeltest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/model.cpp" "${CMAKE_CURRENT_LIST_DIR}/model_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/model_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/model_lua.cpp")
    target_include_directories(kp_modeltest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_modeltest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_modeltest PRIVATE -m32)
    target_link_libraries(kp_modeltest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_modeltest kphasor)
    add_test(NAME kp_modeltest COMMAND kp_modeltest)
    set_tests_properties(kp_modeltest PROPERTIES LABELS "offline;model")
endif()
find_program(KP_MODEL_LUAJIT NAMES luajit REQUIRED)
add_test(NAME model_scene_test COMMAND ${KP_MODEL_LUAJIT}
    "${CMAKE_SOURCE_DIR}/tools/model_scene_test.lua" "${CMAKE_SOURCE_DIR}/scripts/demos/model-memory")
set_tests_properties(model_scene_test PROPERTIES LABELS "offline;model")
