# API tools that consume the runtime LuaJIT build; included after runtime.cmake.
# Keep this file in src/api so CMAKE_CURRENT_LIST_DIR retains its original meaning.

# --- memory ---

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
    add_dependencies(kp_memtest kotorjit)

    # Self-contained: exits 0 when Lua checks plus C++ byte comparisons are 0.
    add_test(NAME kp_memtest COMMAND kp_memtest)

    if(TARGET kp_hooktool)
        add_dependencies(kp_hooktool kotorjit)
    endif()
    if(TARGET kp_manifesttest)
        add_dependencies(kp_manifesttest kotorjit)
    endif()
    if(TARGET kp_luahooktest)
        add_dependencies(kp_luahooktest kotorjit)
    endif()
endif()

# --- model ---

if(UNIX AND NOT WIN32)
    add_executable(kp_modeltest "${CMAKE_SOURCE_DIR}/tools/kp_modeltest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/model.cpp" "${CMAKE_CURRENT_LIST_DIR}/model_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/model_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/model_lua.cpp")
    target_include_directories(kp_modeltest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_modeltest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_modeltest PRIVATE -m32)
    target_link_libraries(kp_modeltest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_modeltest kotorjit)
    add_test(NAME kp_modeltest COMMAND kp_modeltest)
    set_tests_properties(kp_modeltest PROPERTIES LABELS "offline;model")
endif()
find_program(KP_MODEL_LUAJIT NAMES luajit REQUIRED)
add_test(NAME model_scene_test COMMAND ${KP_MODEL_LUAJIT}
    "${CMAKE_SOURCE_DIR}/tools/model_scene_test.lua" "${CMAKE_SOURCE_DIR}/scripts/demos/model-memory")
set_tests_properties(model_scene_test PROPERTIES LABELS "offline;model")

# --- camera ---

if(UNIX AND NOT WIN32)
    add_executable(kp_cameratest "${CMAKE_SOURCE_DIR}/tools/kp_cameratest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/camera.cpp" "${CMAKE_CURRENT_LIST_DIR}/camera_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/camera_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/camera_lua.cpp")
    target_include_directories(kp_cameratest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_cameratest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_cameratest PRIVATE -m32)
    target_link_libraries(kp_cameratest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_cameratest kotorjit)
    add_test(NAME kp_cameratest COMMAND kp_cameratest)
    set_tests_properties(kp_cameratest PROPERTIES LABELS "offline;camera")
endif()
find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
add_test(NAME camera_profile_consistency_test
    COMMAND ${Python3_EXECUTABLE} "${CMAKE_SOURCE_DIR}/tools/camera_profile_consistency_test.py")
set_tests_properties(camera_profile_consistency_test PROPERTIES LABELS "offline;camera")

# --- animation ---

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
 add_dependencies(kp_animationtest kotorjit)
 add_test(NAME kp_animationtest COMMAND kp_animationtest)
 set_tests_properties(kp_animationtest PROPERTIES LABELS "offline;animation")
endif()

find_program(KP_ANIMATION_LUAJIT NAMES luajit REQUIRED)
add_test(NAME animation_scene_test COMMAND ${KP_ANIMATION_LUAJIT}
 "${CMAKE_SOURCE_DIR}/tools/animation_scene_test.lua"
 "${CMAKE_SOURCE_DIR}/scripts/demos/animation-memory/two_actor_freeze.lua")
set_tests_properties(animation_scene_test PROPERTIES LABELS "offline;animation")
