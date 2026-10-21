cmake_minimum_required(VERSION 3.18)
project(vmcore CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CORE ${CMAKE_CURRENT_SOURCE_DIR}/../../../../core)

add_library(vmcore SHARED
    jni_bridge.cpp
    ${CORE}/src/timeline.cpp
    ${CORE}/src/pixel_ops.cpp)
target_include_directories(vmcore PRIVATE ${CORE}/include)
target_compile_options(vmcore PRIVATE -O2 -fvisibility=hidden -Wall -Wextra)
target_link_libraries(vmcore jnigraphics log)
# Android 15+ (páginas de 16 KB)
target_link_options(vmcore PRIVATE -Wl,-z,max-page-size=16384)
