cmake_minimum_required(VERSION 3.18)
project(clawback_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_core src/sauvola.cpp)
target_compile_options(_core PRIVATE
  $<$<CXX_COMPILER_ID:GNU,Clang>:-O3 -Wall -Wextra -Wpedantic>)

install(TARGETS _core DESTINATION clawback_native)
