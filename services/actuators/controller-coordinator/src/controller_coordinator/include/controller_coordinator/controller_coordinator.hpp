// Copyright (c) 2026 Franka Robotics GmbH
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#pragma once

#include <controller_manager_msgs/srv/list_controllers.hpp>
#include <controller_manager_msgs/srv/switch_controller.hpp>
#include <memory>
#include <mutex>
#include <optional>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <string>

namespace controller_coordinator {

/**
 * @brief State enumeration for the controller coordinator
 *
 * Idle: All controllers inactive
 * Ready: Ready-state controller active and running
 * Syncing: Operating controller active, syncing robot state to target joint states
 * Following: Operating controller active, following target joint states
 * Autorecovery: A controller died; attempting to restore the READY state
 */
enum class CoordinatorState { IDLE, READY, SYNCING, FOLLOWING, AUTORECOVERY };

/**
 * @brief Convert CoordinatorState enum to string
 * @param state The state to convert
 * @return String representation of the state
 */
std::string to_string(CoordinatorState state);

/**
 * @brief Controller Coordinator class handling state transitions and controller lifecycle
 *
 * This class manages four states (Idle, Ready, Syncing, Following) and transitions between them
 * based on ROS2 service calls and operating controller sync state. It coordinates controller
 * activation/deactivation through the controller_manager services.
 *
 * State Transitions:
 * - Idle -> Ready: Via "get_ready" service call
 * - Ready -> Syncing: Via "start_operating" service call
 * - Syncing -> Following: Automatic when operating controller reports sync complete
 * - Ready -> Autorecovery -> Ready: Automatic when ready controller dies (one attempt)
 * - Ready -> Autorecovery -> Idle: Automatic when ready controller dies and recovery fails
 * - Syncing/Following -> Autorecovery -> Ready: Automatic when operating controller dies
 * - Syncing/Following -> Autorecovery -> Idle: Automatic when operating controller dies and recovery fails
 * - Following -> Idle: Via "stop" service call
 * - Syncing -> Idle: Via "stop" service call
 * - Ready -> Idle: Via "stop" service call
 *
 * Services:
 * - ~/get_ready: Trigger service to transition from Idle to Ready
 * - ~/start_operating: Trigger service to transition from Ready to Syncing
 * - ~/stop: Trigger service to transition to Idle from any state
 */
class FrankaControllerCoordinator : public rclcpp::Node {
 public:
  // --- ROS parameter defaults ---
  // Used as the default value when declaring ROS parameters and as fallback initialisers.
  static constexpr std::chrono::milliseconds kDefaultServiceTimeout{5000};
  static constexpr std::chrono::milliseconds kDefaultAutorecoveryTimeout{30000};

  // --- Fixed timeouts (not ROS-configurable) ---
  // Single list_controllers call timeout when polling for a controller to appear.
  static constexpr std::chrono::milliseconds kControllerLoadPerCallTimeout{500};
  // Sleep interval between retries in wait_for_controller_loaded.
  static constexpr std::chrono::milliseconds kControllerLoadPollInterval{200};
  // Single-call timeout used to probe whether the controller manager is reachable.
  static constexpr std::chrono::milliseconds kControllerManagerProbeTimeout{200};
  // Hardware-level timeout forwarded to the switch_controller service request.
  static constexpr std::chrono::milliseconds kSwitchControllerHardwareTimeout{5000};

  explicit FrankaControllerCoordinator(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());
  virtual ~FrankaControllerCoordinator();
  CoordinatorState get_state() const;

 private:
  void handle_get_ready(const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
                        std::shared_ptr<std_srvs::srv::Trigger::Response> response);

  void handle_start_operating(const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
                              std::shared_ptr<std_srvs::srv::Trigger::Response> response);

  void handle_stop(const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
                   std::shared_ptr<std_srvs::srv::Trigger::Response> response);

  void handle_start_autorecovery(const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
                          std::shared_ptr<std_srvs::srv::Trigger::Response> response);

  bool transition_to_ready();
  bool transition_to_syncing();
  void transition_to_following();
  bool transition_to_idle();
  bool transition_autorecovery_to_ready();
  void monitor_autorecovery_cycle();

  bool switch_controllers(const std::vector<std::string>& activate_controllers,
                          const std::vector<std::string>& deactivate_controllers,
                          bool strict = true);
  std::optional<bool> is_controller_active(const std::string& controller_name);
  bool is_controller_loaded(const std::string& controller_name,
                             std::chrono::milliseconds timeout = kControllerLoadPerCallTimeout);
  bool wait_for_controller_loaded(const std::string& controller_name,
                                   std::chrono::milliseconds total_timeout = kDefaultServiceTimeout);
  bool is_controller_manager_available(
      std::chrono::milliseconds probe_timeout = kControllerManagerProbeTimeout);
  void monitor_operating_controller();
  void on_controller_state_received(const std_msgs::msg::String& msg);

  void declare_parameters();
  void initialize_service_clients();
  void initialize_service_servers();
  void initialize_controller_state_subscriber();
  void publish_state();

  CoordinatorState current_state_;
  std::string ready_controller_name_;
  std::string operating_controller_name_;
  std::string controller_manager_namespace_;
  double monitor_rate_hz_;
  std::chrono::milliseconds service_timeout_;

  rclcpp::Client<controller_manager_msgs::srv::SwitchController>::SharedPtr
      switch_controller_client_;
  rclcpp::Client<controller_manager_msgs::srv::ListControllers>::SharedPtr list_controllers_client_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr get_ready_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr start_operating_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr stop_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr autorecover_service_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_publisher_;
  rclcpp::TimerBase::SharedPtr controller_monitor_timer_;
  rclcpp::TimerBase::SharedPtr state_publish_timer_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr controller_state_subscriber_;
  std::string last_controller_state_;
  std::optional<std::chrono::steady_clock::time_point> autorecovery_started_;
  std::chrono::milliseconds autorecovery_timeout_{kDefaultAutorecoveryTimeout};
  rclcpp::CallbackGroup::SharedPtr client_callback_group_;
  rclcpp::CallbackGroup::SharedPtr service_callback_group_;
  mutable std::mutex state_mutex_;
};

}  // namespace controller_coordinator
