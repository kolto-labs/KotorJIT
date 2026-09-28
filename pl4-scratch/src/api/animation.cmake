if(UNIX AND NOT WIN32)
 add_executable(kp_animationtest "${CMAKE_SOURCE_DIR}/tools/kp_animationtest.cpp"
  "${CMAKE_CURRENT_LIST_DIR}/animation.cpp" "${CMAKE_CURRENT_LIST_DIR}/animation_profiles.cpp"
  "${CMAKE_CURRENT_LIST_DIR}/animation_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/animation_lua.cpp"
  "${CMAKE_CURRENT_LIST_DIR}/model.cpp" "${CMAKE_CURRENT_LIST_DIR}/model_profiles.cpp"
  "${CMAKE_CURRENT_LIST_DIR}/model_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/model_lua.cpp")
 target_include_directories(kp_animationtest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
 target_compile_options(kp_animationtest PRIVATE -m32 -Wall -Wextra)
 target_link_options(kp_animationtest PRIVATE -m32)
 target_link_libraries(kp_animationtest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
 add_dependencies(kp_animationtest kphasor)
 add_test(NAME kp_animationtest COMMAND kp_animationtest)
 set_tests_properties(kp_animationtest PROPERTIES LABELS "offline;animation")
endif()

find_program(KP_ANIMATION_LUAJIT NAMES luajit REQUIRED)
add_test(NAME animation_scene_test COMMAND ${KP_ANIMATION_LUAJIT}
 "${CMAKE_SOURCE_DIR}/tools/animation_scene_test.lua"
 "${CMAKE_SOURCE_DIR}/scripts/demos/animation-memory/two_actor_freeze.lua")
set_tests_properties(animation_scene_test PROPERTIES LABELS "offline;animation")
