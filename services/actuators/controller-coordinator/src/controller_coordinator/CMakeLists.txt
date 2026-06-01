cmake_minimum_required(VERSION 3.5)
project(controller_coordinator)

# Default to C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE
      "Debug"
      CACHE STRING "Build type (default is Debug)" FORCE)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(--coverage -O0 -g)
    add_link_options(--coverage)
  endif()
endif()

option(CHECK_TIDY "Adds clang-tidy tests" OFF)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(controller_manager_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(std_msgs REQUIRED)

add_library(${PROJECT_NAME} SHARED src/controller_coordinator.cpp)
target_include_directories(
  ${PROJECT_NAME} PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
                         $<INSTALL_INTERFACE:include>)
ament_target_dependencies(${PROJECT_NAME} rclcpp controller_manager_msgs
                          std_srvs std_msgs)

add_executable(controller_coordinator_node src/controller_coordinator_node.cpp)
target_link_libraries(controller_coordinator_node ${PROJECT_NAME})
ament_target_dependencies(controller_coordinator_node rclcpp)

install(
  TARGETS ${PROJECT_NAME} controller_coordinator_node
  RUNTIME DESTINATION lib/${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib)

install(DIRECTORY include/ DESTINATION include)

install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME})
ament_export_dependencies(rclcpp controller_manager_msgs std_srvs)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_clang_format REQUIRED)
  find_package(ament_cmake_copyright REQUIRED)
  find_package(ament_cmake_cppcheck REQUIRED)
  find_package(ament_cmake_lint_cmake REQUIRED)
  find_package(ament_cmake_xmllint REQUIRED)

  set(CPP_DIRECTORIES src include test)

  ament_cppcheck(${CPP_DIRECTORIES})
  ament_lint_cmake(CMakeLists.txt)
  ament_xmllint()
  ament_clang_format(
    CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/../../.clang-format
    ${CPP_DIRECTORIES})
  ament_copyright(${CPP_DIRECTORIES} package.xml)
endif()

if(CHECK_TIDY)
  find_package(ament_cmake_clang_tidy REQUIRED)
  set(ament_cmake_clang_tidy_CONFIG_FILE
      ${CMAKE_CURRENT_SOURCE_DIR}/../../.clang-tidy)
  ament_clang_tidy(${CMAKE_BINARY_DIR})
endif()

ament_package()
