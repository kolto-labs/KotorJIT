# kp.camera Stage 1 checked core and Lua surface; production sources ship in runtime.cmake.
if(UNIX AND NOT WIN32)
    add_executable(kp_cameratest "${CMAKE_SOURCE_DIR}/tools/kp_cameratest.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/camera.cpp" "${CMAKE_CURRENT_LIST_DIR}/camera_profiles.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/camera_backend.cpp" "${CMAKE_CURRENT_LIST_DIR}/camera_lua.cpp")
    target_include_directories(kp_cameratest PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/third_party/luajit/src")
    target_compile_options(kp_cameratest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_cameratest PRIVATE -m32)
    target_link_libraries(kp_cameratest PRIVATE "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a" m dl)
    add_dependencies(kp_cameratest kphasor)
    add_test(NAME kp_cameratest COMMAND kp_cameratest)
    set_tests_properties(kp_cameratest PROPERTIES LABELS "offline;camera")
endif()
find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
add_test(NAME camera_profile_consistency_test
    COMMAND ${Python3_EXECUTABLE} "${CMAKE_SOURCE_DIR}/tools/camera_profile_consistency_test.py")
set_tests_properties(camera_profile_consistency_test PROPERTIES LABELS "offline;camera")
