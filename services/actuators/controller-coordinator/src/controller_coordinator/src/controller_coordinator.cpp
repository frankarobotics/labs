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

#include "controller_coordinator/controller_coordinator.hpp"

#include <chrono>
#include <thread>

namespace controller_coordinator {

std::string to_string(CoordinatorState state) {
  switch (state) {
    case CoordinatorState::IDLE:
      return "IDLE";
    case CoordinatorState::READY:
      return "READY";
    case CoordinatorState::SYNCING:
      return "SYNCING";
    case CoordinatorState::FOLLOWING:
      return "FOLLOWING";
    default:
      return "UNKNOWN";
  }
}

FrankaControllerCoordinator::FrankaControllerCoordinator(const rclcpp::NodeOptions& options)
    : Node("controller_coordinator", options), current_state_(CoordinatorState::IDLE) {
  client_callback_group_ =
      this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  service_callback_group_ =
      this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

  declare_parameters();
  initialize_service_clients();
  initialize_service_servers();
  initialize_controller_state_subscriber();

  auto qos = rclcpp::QoS(rclcpp::KeepLast(1)).transient_local();
  state_publisher_ = this->create_publisher<std_msgs::msg::String>("~/state", qos);

  controller_monitor_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(1.0 / monitor_rate_hz_),
      std::bind(&FrankaControllerCoordinator::monitor_operating_controller, this));

  state_publish_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(1.0 / monitor_rate_hz_),
      std::bind(&FrankaControllerCoordinator::publish_state, this));

  publish_state();
  RCLCPP_INFO(this->get_logger(), "Franka Controller Coordinator initialized in IDLE state");
}

FrankaControllerCoordinator::~FrankaControllerCoordinator() {
  if (controller_monitor_timer_) {
    controller_monitor_timer_->cancel();
  }
  if (state_publish_timer_) {
    state_publish_timer_->cancel();
  }
  transition_to_idle();
  RCLCPP_INFO(this->get_logger(), "Franka Controller Coordinator shutting down");
}

CoordinatorState FrankaControllerCoordinator::get_state() const {
  return current_state_;
}

void FrankaControllerCoordinator::declare_parameters() {
  this->declare_parameter("ready_controller", "ready_controller");
  this->declare_parameter("operating_controller", "operating_controller");
  this->declare_parameter("controller_manager_namespace", "/controller_manager");
  this->declare_parameter("monitor_rate_hz", 10.0);
  this->declare_parameter("service_timeout_ms", 5000);

  ready_controller_name_ = this->get_parameter("ready_controller").as_string();
  operating_controller_name_ = this->get_parameter("operating_controller").as_string();
  controller_manager_namespace_ = this->get_parameter("controller_manager_namespace").as_string();
  monitor_rate_hz_ = this->get_parameter("monitor_rate_hz").as_double();
  service_timeout_ = std::chrono::milliseconds(this->get_parameter("service_timeout_ms").as_int());

  RCLCPP_INFO(this->get_logger(), "Controller manager namespace: %s", controller_manager_namespace_.c_str());
  RCLCPP_INFO(this->get_logger(), "Ready controller: %s", ready_controller_name_.c_str());
  RCLCPP_INFO(this->get_logger(), "Operating controller: %s", operating_controller_name_.c_str());
}

void FrankaControllerCoordinator::initialize_service_clients() {
  std::string switch_controller_service = controller_manager_namespace_ + "/switch_controller";
  std::string list_controllers_service = controller_manager_namespace_ + "/list_controllers";

  RCLCPP_INFO(this->get_logger(), "Waiting for switch controller service: %s", switch_controller_service.c_str());
  RCLCPP_INFO(this->get_logger(), "Waiting for list controllers service: %s", list_controllers_service.c_str());

  switch_controller_client_ = this->create_client<controller_manager_msgs::srv::SwitchController>(
      switch_controller_service, rmw_qos_profile_services_default,
      client_callback_group_);

  list_controllers_client_ = this->create_client<controller_manager_msgs::srv::ListControllers>(
      list_controllers_service, rmw_qos_profile_services_default,
      client_callback_group_);

  if (!switch_controller_client_->wait_for_service(service_timeout_)) {
    RCLCPP_WARN(this->get_logger(), "Switch controller service not yet available: %s", switch_controller_service.c_str());
  }

  if (!list_controllers_client_->wait_for_service(service_timeout_)) {
    RCLCPP_WARN(this->get_logger(), "List controllers service not yet available: %s", list_controllers_service.c_str());
  }
}

void FrankaControllerCoordinator::initialize_service_servers() {
  get_ready_service_ = this->create_service<std_srvs::srv::Trigger>(
      "~/get_ready", std::bind(&FrankaControllerCoordinator::handle_get_ready, this,
                               std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, service_callback_group_);

  start_operating_service_ = this->create_service<std_srvs::srv::Trigger>(
      "~/start_operating", std::bind(&FrankaControllerCoordinator::handle_start_operating, this,
                                     std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, service_callback_group_);

  stop_service_ = this->create_service<std_srvs::srv::Trigger>(
      "~/stop", std::bind(&FrankaControllerCoordinator::handle_stop, this, std::placeholders::_1,
                          std::placeholders::_2),
      rmw_qos_profile_services_default, service_callback_group_);
}

void FrankaControllerCoordinator::initialize_controller_state_subscriber() {
  std::string ns = this->get_namespace();
  std::string controller_state_topic =
      (ns == "/" ? "" : ns) + "/" + operating_controller_name_ + "/state";

  auto qos = rclcpp::QoS(rclcpp::KeepLast(1)).transient_local();
  controller_state_subscriber_ = this->create_subscription<std_msgs::msg::String>(
      controller_state_topic, qos,
      std::bind(&FrankaControllerCoordinator::on_controller_state_received, this, std::placeholders::_1));

  RCLCPP_INFO(this->get_logger(), "Subscribed to sync state topic: %s", controller_state_topic.c_str());
}

void FrankaControllerCoordinator::publish_state() {
  auto msg = std_msgs::msg::String();
  msg.data = to_string(current_state_);
  state_publisher_->publish(msg);
}

void FrankaControllerCoordinator::handle_get_ready(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response) {
  response->success = transition_to_ready();
  response->message =
      response->success ? "Transitioned to READY state" : "Failed to transition to READY state";
  RCLCPP_INFO(this->get_logger(), "%s", response->message.c_str());
}

void FrankaControllerCoordinator::handle_start_operating(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response) {
  response->success = transition_to_syncing();
  response->message = response->success ? "Transitioned to SYNCING state"
                                        : "Failed to transition to SYNCING state";
  RCLCPP_INFO(this->get_logger(), "%s", response->message.c_str());
}

void FrankaControllerCoordinator::handle_stop(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response) {
  response->success = transition_to_idle();
  response->message =
      response->success ? "Transitioned to IDLE state" : "Failed to transition to IDLE state";
  RCLCPP_INFO(this->get_logger(), "%s", response->message.c_str());
}

bool FrankaControllerCoordinator::transition_to_ready() {
  std::unique_lock<std::mutex> lock(state_mutex_);

  if (current_state_ == CoordinatorState::READY) {
    RCLCPP_INFO(this->get_logger(), "Already in READY state");
    return true;
  }
  if (current_state_ != CoordinatorState::IDLE) {
    RCLCPP_WARN(this->get_logger(), "Can only transition to READY from IDLE state. Current state: %s",
                to_string(current_state_).c_str());
    return false;
  }

  RCLCPP_INFO(this->get_logger(), "Transitioning IDLE -> READY");

  if (!switch_controller_client_->wait_for_service(service_timeout_) ||
      !list_controllers_client_->wait_for_service(service_timeout_)) {
    RCLCPP_ERROR(this->get_logger(), "Controller manager service is not available");
    return false;
  }

  if (!wait_for_controller_loaded(ready_controller_name_)) {
    return false;
  }

  auto already_active = is_controller_active(ready_controller_name_);
  if (already_active.has_value() && already_active.value()) {
    RCLCPP_INFO(this->get_logger(), "Ready controller '%s' is already active, skipping switch",
                ready_controller_name_.c_str());
  } else {
    if (!switch_controllers({ready_controller_name_}, {})) {
      RCLCPP_ERROR(this->get_logger(), "Failed to activate ready controller");
      return false;
    }
  }

  current_state_ = CoordinatorState::READY;
  publish_state();
  return true;
}

bool FrankaControllerCoordinator::transition_to_syncing() {
  std::unique_lock<std::mutex> lock(state_mutex_);

  if (current_state_ == CoordinatorState::SYNCING || current_state_ == CoordinatorState::FOLLOWING) {
    RCLCPP_INFO(this->get_logger(), "Already in %s state", to_string(current_state_).c_str());
    return true;
  }
  if (current_state_ != CoordinatorState::READY) {
    RCLCPP_WARN(this->get_logger(), "Can only start operating from READY state. Current state: %s",
                to_string(current_state_).c_str());
    return false;
  }

  RCLCPP_INFO(this->get_logger(), "Transitioning READY -> SYNCING");

  if (!switch_controller_client_->wait_for_service(service_timeout_) ||
      !list_controllers_client_->wait_for_service(service_timeout_)) {
    RCLCPP_ERROR(this->get_logger(), "Controller manager service is not available");
    return false;
  }

  if (!switch_controllers({operating_controller_name_}, {ready_controller_name_})) {
    RCLCPP_ERROR(this->get_logger(), "Failed to switch to operating controller");
    return false;
  }

  // If the controller already reported FOLLOWING (e.g. sync_after_activation is disabled),
  // transition directly to FOLLOWING without publishing the transient SYNCING state.
  if (last_controller_state_ == "FOLLOWING") {
    current_state_ = CoordinatorState::FOLLOWING;
  } else {
    current_state_ = CoordinatorState::SYNCING;
  }
  publish_state();
  return true;
}

void FrankaControllerCoordinator::transition_to_following() {
  RCLCPP_INFO(this->get_logger(), "Transitioning SYNCING -> FOLLOWING");
  std::lock_guard<std::mutex> lock(state_mutex_);
  current_state_ = CoordinatorState::FOLLOWING;
  publish_state();
}

void FrankaControllerCoordinator::on_controller_state_received(const std_msgs::msg::String& msg) {
  last_controller_state_ = msg.data;
  std::unique_lock<std::mutex> lock(state_mutex_);
  bool should_follow = (current_state_ == CoordinatorState::SYNCING && msg.data == "FOLLOWING");
  lock.unlock();
  if (should_follow) {
    transition_to_following();
  }
}

bool FrankaControllerCoordinator::transition_to_idle() {
  std::unique_lock<std::mutex> lock(state_mutex_);

  if (current_state_ == CoordinatorState::IDLE) {
    RCLCPP_INFO(this->get_logger(), "Already in IDLE state");
    return true;
  }

  RCLCPP_INFO(this->get_logger(), "Transitioning to IDLE");

  std::vector<std::string> deactivate_controllers;
  if (current_state_ == CoordinatorState::READY) {
    deactivate_controllers.push_back(ready_controller_name_);
  } else if (current_state_ == CoordinatorState::SYNCING || current_state_ == CoordinatorState::FOLLOWING) {
    deactivate_controllers.push_back(operating_controller_name_);
  }

  current_state_ = CoordinatorState::IDLE;
  publish_state();
  lock.unlock();

  if (!deactivate_controllers.empty()) {
    if (is_controller_manager_available()) {
      if (!switch_controllers({}, deactivate_controllers, false)) {
        RCLCPP_ERROR(this->get_logger(), "Failed to deactivate controllers");
        // Continue anyway — state is already IDLE
      }
    } else {
      RCLCPP_WARN(this->get_logger(),
                  "Controller manager not available, transitioning to IDLE without deactivating "
                  "controllers");
    }
  }

  return true;
}

bool FrankaControllerCoordinator::transition_following_to_ready() {
  RCLCPP_INFO(this->get_logger(), "Transitioning to READY from %s", to_string(current_state_).c_str());

  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!switch_controllers({ready_controller_name_}, {operating_controller_name_}, false)) {
    RCLCPP_ERROR(this->get_logger(), "Failed to switch back to ready controller");
    return false;
  }

  current_state_ = CoordinatorState::READY;
  publish_state();
  return true;
}

bool FrankaControllerCoordinator::switch_controllers(
    const std::vector<std::string>& activate_controllers,
    const std::vector<std::string>& deactivate_controllers,
    bool strict) {
  auto request = std::make_shared<controller_manager_msgs::srv::SwitchController::Request>();
  request->activate_controllers = activate_controllers;
  request->deactivate_controllers = deactivate_controllers;
  request->strictness = strict ? 2 : 1;
  request->activate_asap = true;
  request->timeout = rclcpp::Duration(5, 0);

  auto future = switch_controller_client_->async_send_request(request);

  if (future.wait_for(service_timeout_) != std::future_status::ready) {
    RCLCPP_ERROR(this->get_logger(), "Switch controller service call timed out");
    return false;
  }

  auto result = future.get();
  if (!result->ok) {
    RCLCPP_ERROR(this->get_logger(), "Switch controller service call failed");
    return false;
  }

  return true;
}

std::optional<bool> FrankaControllerCoordinator::is_controller_active(const std::string& controller_name) {
  auto request = std::make_shared<controller_manager_msgs::srv::ListControllers::Request>();
  auto future = list_controllers_client_->async_send_request(request);

  if (future.wait_for(service_timeout_) != std::future_status::ready) {
    RCLCPP_WARN(this->get_logger(), "List controllers service call timed out, skipping monitor cycle");
    return std::nullopt;  // Unknown — don't act on this
  }

  auto result = future.get();
  for (const auto& controller : result->controller) {
    if (controller.name == controller_name) {
      return controller.state == "active";
    }
  }

  return false;  // Confirmed not present / not active
}

bool FrankaControllerCoordinator::is_controller_loaded(const std::string& controller_name) {
  auto request = std::make_shared<controller_manager_msgs::srv::ListControllers::Request>();
  auto future = list_controllers_client_->async_send_request(request);

  if (future.wait_for(service_timeout_) != std::future_status::ready) {
    RCLCPP_WARN(this->get_logger(), "List controllers service call timed out");
    return false;
  }

  auto result = future.get();
  for (const auto& controller : result->controller) {
    if (controller.name == controller_name) {
      return true;
    }
  }
  return false;
}

bool FrankaControllerCoordinator::wait_for_controller_loaded(const std::string& controller_name) {
  RCLCPP_INFO(this->get_logger(), "Waiting for controller '%s' to be loaded...", controller_name.c_str());
  auto deadline = std::chrono::steady_clock::now() + service_timeout_;
  while (std::chrono::steady_clock::now() < deadline) {
    if (is_controller_loaded(controller_name)) {
      RCLCPP_INFO(this->get_logger(), "Controller '%s' is loaded", controller_name.c_str());
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }
  RCLCPP_ERROR(this->get_logger(), "Timed out waiting for controller '%s' to be loaded", controller_name.c_str());
  return false;
}

bool FrankaControllerCoordinator::is_controller_manager_available(
    std::chrono::milliseconds probe_timeout) {
  auto request = std::make_shared<controller_manager_msgs::srv::ListControllers::Request>();
  auto future = list_controllers_client_->async_send_request(request);
  return future.wait_for(probe_timeout) == std::future_status::ready;
}

void FrankaControllerCoordinator::monitor_operating_controller() {
  // Snapshot state without blocking. If a transition holds the lock, skip this
  // cycle — the next one (100 ms later) will see the completed state.
  CoordinatorState state;
  {
    std::unique_lock<std::mutex> lock(state_mutex_, std::try_to_lock);
    if (!lock.owns_lock()) {
      return;
    }
    state = current_state_;
  }

  if (state == CoordinatorState::IDLE) {
    return;
  }

  if (!is_controller_manager_available()) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    if (current_state_ != state) {
      return;
    }
    RCLCPP_ERROR(this->get_logger(), "Controller manager is not available, transitioning to IDLE");
    current_state_ = CoordinatorState::IDLE;
    publish_state();
    return;
  }

  const std::string& controller_to_check =
      (state == CoordinatorState::READY) ? ready_controller_name_ : operating_controller_name_;

  auto active = is_controller_active(controller_to_check);

  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    if (current_state_ != state) {
      return;
    }
  }

  if (!active.has_value()) {
    return;  // Timeout — uncertain, skip this cycle
  }

  if (active.value()) {
    return;  // Controller is healthy, nothing to do
  }

  if (state == CoordinatorState::READY) {
    RCLCPP_WARN(this->get_logger(), "Ready controller is not active, transitioning to IDLE");
    transition_to_idle();
  } else {
    RCLCPP_WARN(this->get_logger(), "Operating controller is not active, transitioning to READY");
    if (!transition_following_to_ready()) {
      RCLCPP_ERROR(this->get_logger(), "Failed to transition to READY state after controller death");
      transition_to_idle();
    }
  }
}

}  // namespace controller_coordinator
