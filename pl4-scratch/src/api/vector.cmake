# Build rules for kp.vec's offline test.
#
# An include() fragment in the house style of src/api/support.cmake. It is
# self-contained on purpose: it sets its own language level, flags and include
# directories, so it gives the same target whether it is included from
# CMakeLists.txt beside the other api fragments or injected straight after
# project() with -DCMAKE_PROJECT_KotorPhasor_INCLUDE=<this file> (which is how it
# was built before it had a line in CMakeLists.txt).
#
# kp_vectortest links kphasor for the routine bridge (kp::api::call, bind,
# push_kp_table) and compiles vector.cpp itself, so it tests the source even
# before kphasor carries it. Both names resolve at generate time, so the include
# order relative to runtime.cmake does not matter.

set(KP_VEC_API_DIR  "${CMAKE_CURRENT_LIST_DIR}")
set(KP_VEC_SRC_ROOT "${CMAKE_CURRENT_LIST_DIR}/..")
set(KP_VEC_TOOLS    "${CMAKE_CURRENT_LIST_DIR}/../../tools")
set(KP_VEC_LUAJIT   "${CMAKE_BINARY_DIR}/luajit32/src/libluajit.a")

if(UNIX AND NOT WIN32)
    add_executable(kp_vectortest
        "${KP_VEC_TOOLS}/kp_vectortest.cpp"
        "${KP_VEC_API_DIR}/vector.cpp"
    )
    target_compile_features(kp_vectortest PRIVATE cxx_std_20)
    target_include_directories(kp_vectortest PRIVATE
        "${KP_VEC_SRC_ROOT}" "${CMAKE_BINARY_DIR}/luajit32/src")
    target_compile_options(kp_vectortest PRIVATE -m32 -Wall -Wextra)
    target_link_options(kp_vectortest PRIVATE -m32)
    add_dependencies(kp_vectortest kphasor)
    target_link_libraries(kp_vectortest PRIVATE kphasor "${KP_VEC_LUAJIT}" m dl)
    add_test(NAME kp_vectortest COMMAND kp_vectortest)
endif()
