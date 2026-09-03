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
#include <lifecycle_msgs/msg/state.hpp>
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
    case CoordinatorState::AUTORECOVERY:
      return "AUTORECOVERY";
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
  robot_state_callback_group_ =
      this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

  declare_parameters();
  initialize_service_clients();
  initialize_service_servers();
  initialize_controller_state_subscriber();
  initialize_robot_state_subscriber();

  auto qos = rclcpp::QoS(rclcpp::KeepLast(1)).transient_local();
  state_publisher_ = this->create_publisher<std_msgs::msg::String>("~/state", qos);

  controller_monitor_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(1.0 / monitor_rate_hz_),
      std::bind(&FrankaControllerCoordinator::monitor_operating_controller, this));

  state_publish_timer_ = this->create_wall_timer(
      std::chrono::duration<double>(1.0 / monitor_rate_hz_),
      std::bind(&FrankaControllerCoordinator::publish_state, this));

  auto robot_state_monitor_period =
      std::max(kMinRobotStateMonitorPeriod, robot_state_stale_timeout_ms_ / 2);
  robot_state_monitor_timer_ = this->create_wall_timer(
      robot_state_monitor_period,
      std::bind(&FrankaControllerCoordinator::check_robot_state_staleness, this),
      robot_state_callback_group_);

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
  if (robot_state_monitor_timer_) {
    robot_state_monitor_timer_->cancel();
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
  this->declare_parameter("service_timeout_ms",
                           static_cast<int>(kDefaultServiceTimeout.count()));
  this->declare_parameter("autorecovery_timeout_ms",
                           static_cast<int>(kDefaultAutorecoveryTimeout.count()));
  this->declare_parameter("robot_state_stale_timeout_ms",
                           static_cast<int>(kDefaultRobotStateStaleTimeout.count()));

  ready_controller_name_ = this->get_parameter("ready_controller").as_string();
  operating_controller_name_ = this->get_parameter("operating_controller").as_string();
  controller_manager_namespace_ = this->get_parameter("controller_manager_namespace").as_string();
  monitor_rate_hz_ = this->get_parameter("monitor_rate_hz").as_double();
  service_timeout_ = std::chrono::milliseconds(this->get_parameter("service_timeout_ms").as_int());
  autorecovery_timeout_ =
      std::chrono::milliseconds(this->get_parameter("autorecovery_timeout_ms").as_int());
  robot_state_stale_timeout_ms_ =
      std::chrono::milliseconds(this->get_parameter("robot_state_stale_timeout_ms").as_int());

  RCLCPP_INFO(this->get_logger(), "Controller manager namespace: %s", controller_manager_namespace_.c_str());
  RCLCPP_INFO(this->get_logger(), "Ready controller: %s", ready_controller_name_.c_str());
  RCLCPP_INFO(this->get_logger(), "Operating controller: %s", operating_controller_name_.c_str());
  RCLCPP_INFO(this->get_logger(), "Autorecovery timeout: %ld ms", autorecovery_timeout_.count());
  RCLCPP_INFO(this->get_logger(), "Robot state stale timeout: %ld ms",
              robot_state_stale_timeout_ms_.count());
}

void FrankaControllerCoordinator::initialize_service_clients() {
  std::string switch_controller_service = controller_manager_namespace_ + "/switch_controller";
  std::string list_controllers_service = controller_manager_namespace_ + "/list_controllers";
  std::string list_hardware_components_service =
      controller_manager_namespace_ + "/list_hardware_components";
  std::string set_hardware_component_state_service =
      controller_manager_namespace_ + "/set_hardware_component_state";

  RCLCPP_INFO(this->get_logger(), "Waiting for switch controller service: %s", switch_controller_service.c_str());
  RCLCPP_INFO(this->get_logger(), "Waiting for list controllers service: %s", list_controllers_service.c_str());

  switch_controller_client_ = this->create_client<controller_manager_msgs::srv::SwitchController>(
      switch_controller_service, rmw_qos_profile_services_default,
      client_callback_group_);

  list_controllers_client_ = this->create_client<controller_manager_msgs::srv::ListControllers>(
      list_controllers_service, rmw_qos_profile_services_default,
      client_callback_group_);

  list_hardware_components_client_ =
      this->create_client<controller_manager_msgs::srv::ListHardwareComponents>(
          list_hardware_components_service, rmw_qos_profile_services_default,
          client_callback_group_);

  set_hardware_component_state_client_ =
      this->create_client<controller_manager_msgs::srv::SetHardwareComponentState>(
          set_hardware_component_state_service, rmw_qos_profile_services_default,
          client_callback_group_);

  std::string error_recovery_action = "action_server/error_recovery";
  error_recovery_client_ =
      rclcpp_action::create_client<franka_msgs::action::ErrorRecovery>(
          this, error_recovery_action, client_callback_group_);
  RCLCPP_INFO(this->get_logger(), "Error recovery action: %s", error_recovery_action.c_str());

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

  autorecover_service_ = this->create_service<std_srvs::srv::Trigger>(
      "~/start_autorecovery", std::bind(&FrankaControllerCoordinator::handle_start_autorecovery, this,
                                 std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, service_callback_group_);
}

void FrankaControllerCoordinator::initialize_controller_state_subscriber() {
  std::string controller_state_topic = operating_controller_name_ + "/state";

  auto qos = rclcpp::QoS(rclcpp::KeepLast(1)).transient_local();
  controller_state_subscriber_ = this->create_subscription<std_msgs::msg::String>(
      controller_state_topic, qos,
      std::bind(&FrankaControllerCoordinator::on_controller_state_received, this, std::placeholders::_1));

  RCLCPP_INFO(this->get_logger(), "Subscribed to sync state topic: %s", controller_state_topic.c_str());
}

void FrankaControllerCoordinator::initialize_robot_state_subscriber() {
  std::string robot_state_topic = "franka_robot_state_broadcaster/robot_state";

  rclcpp::SubscriptionOptions opts;
  opts.callback_group = robot_state_callback_group_;
  robot_state_subscriber_ = this->create_subscription<franka_msgs::msg::FrankaRobotState>(
      robot_state_topic, rclcpp::SystemDefaultsQoS(),
      std::bind(&FrankaControllerCoordinator::on_robot_state_received, this,
                std::placeholders::_1),
      opts);

  RCLCPP_INFO(this->get_logger(), "Subscribed to robot state topic: %s", robot_state_topic.c_str());
}

void FrankaControllerCoordinator::on_robot_state_received(
    const franka_msgs::msg::FrankaRobotState& msg) {
  last_robot_state_ns_.store(std::chrono::steady_clock::now().time_since_epoch().count(),
                             std::memory_order_relaxed);

  if (msg.robot_mode != franka_msgs::msg::FrankaRobotState::ROBOT_MODE_REFLEX) {
    return;
  }

  std::lock_guard<std::mutex> lock(state_mutex_);
  if (current_state_ != CoordinatorState::READY &&
      current_state_ != CoordinatorState::SYNCING &&
      current_state_ != CoordinatorState::FOLLOWING) {
    return;
  }

  RCLCPP_WARN(this->get_logger(),
              "Reflex detected via robot state, entering AUTORECOVERY from %s",
              to_string(current_state_).c_str());
  autorecovery_started_ = std::chrono::steady_clock::now();
  autorecovery_retry_not_before_ = std::chrono::steady_clock::time_point{};
  autorecovery_pending_hardware_deactivation_ = false;
  current_state_ = CoordinatorState::AUTORECOVERY;
  last_robot_state_ns_.store(0, std::memory_order_relaxed);
  publish_state();
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

void FrankaControllerCoordinator::handle_start_autorecovery(
    const std::shared_ptr<std_srvs::srv::Trigger::Request>,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response) {
  std::lock_guard<std::mutex> lock(state_mutex_);

  if (current_state_ == CoordinatorState::AUTORECOVERY ||
      current_state_ == CoordinatorState::READY) {
    // Already recovering or already at the target state — nothing to do.
    response->success = true;
    response->message = "Already in " + to_string(current_state_) + " state";
    RCLCPP_DEBUG(this->get_logger(), "autorecover: %s", response->message.c_str());
    return;
  }

  if (current_state_ == CoordinatorState::IDLE) {
    response->success = false;
    response->message = "Cannot autorecover from IDLE state";
    RCLCPP_WARN(this->get_logger(), "%s", response->message.c_str());
    return;
  }

  // FOLLOWING or SYNCING: enter AUTORECOVERY immediately and let the monitor
  // handle the activation of the ready controller in its next cycle. We accept
  // that the next cycle comes with a small delay, but it keeps the logic simpler.
  RCLCPP_INFO(this->get_logger(), "autorecover requested from %s, entering AUTORECOVERY",
              to_string(current_state_).c_str());
  autorecovery_started_ = std::chrono::steady_clock::now();
  autorecovery_retry_not_before_ = std::chrono::steady_clock::time_point{};
  autorecovery_pending_hardware_deactivation_ = false;
  current_state_ = CoordinatorState::AUTORECOVERY;
  last_robot_state_ns_.store(0, std::memory_order_relaxed);
  publish_state();
  response->success = true;
  response->message = "Entered AUTORECOVERY state";
}

bool FrankaControllerCoordinator::transition_to_ready() {
  std::unique_lock<std::mutex> lock(state_mutex_);

  if (current_state_ == CoordinatorState::READY) {
    RCLCPP_DEBUG(this->get_logger(), "Already in READY state");
    return true;
  }

  if (current_state_ == CoordinatorState::AUTORECOVERY) {
    RCLCPP_INFO(this->get_logger(),
                "get_ready called during AUTORECOVERY — recovery is already in progress.");
    return false;
  }

  RCLCPP_INFO(this->get_logger(), "Transitioning %s -> READY", to_string(current_state_).c_str());

  if (!switch_controller_client_->wait_for_service(service_timeout_) ||
      !list_controllers_client_->wait_for_service(service_timeout_)) {
    RCLCPP_ERROR(this->get_logger(), "Controller manager service is not available");
    return false;
  }

  if (current_state_ == CoordinatorState::FOLLOWING ||
      current_state_ == CoordinatorState::SYNCING) {
    // Deactivate the operating controller and activate the ready controller.
    if (!switch_controllers({ready_controller_name_}, {operating_controller_name_}, false)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to switch from operating to ready controller");
      return false;
    }
  } else {
    if (!wait_for_controller_loaded(ready_controller_name_)) {
      return false;
    }

    auto already_active = is_controller_active(ready_controller_name_);
    if (already_active.has_value() && already_active.value()) {
      RCLCPP_DEBUG(this->get_logger(), "Ready controller '%s' is already active, skipping switch",
                  ready_controller_name_.c_str());
    } else {
      if (!switch_controllers({ready_controller_name_}, {})) {
        RCLCPP_ERROR(this->get_logger(), "Failed to activate ready controller");
        return false;
      }
    }
  }

  current_state_ = CoordinatorState::READY;
  publish_state();
  return true;
}

bool FrankaControllerCoordinator::transition_to_syncing() {
  std::unique_lock<std::mutex> lock(state_mutex_);

  if (current_state_ == CoordinatorState::SYNCING || current_state_ == CoordinatorState::FOLLOWING) {
    RCLCPP_DEBUG(this->get_logger(), "Already in %s state", to_string(current_state_).c_str());
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
    RCLCPP_DEBUG(this->get_logger(), "Already in IDLE state");
    return true;
  }

  RCLCPP_INFO(this->get_logger(), "Transitioning to IDLE");

  std::vector<std::string> deactivate_controllers;
  
  if (current_state_ == CoordinatorState::READY ||
      current_state_ == CoordinatorState::SYNCING ||
      current_state_ == CoordinatorState::FOLLOWING ||
      current_state_ == CoordinatorState::AUTORECOVERY) {
    deactivate_controllers.push_back(ready_controller_name_);
    deactivate_controllers.push_back(operating_controller_name_);
  }

  current_state_ = CoordinatorState::IDLE;
  last_robot_state_ns_.store(0, std::memory_order_relaxed);
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

bool FrankaControllerCoordinator::transition_autorecovery_to_ready() {
  RCLCPP_INFO(this->get_logger(),
              "Autorecovery: activating '%s', deactivating '%s'",
              ready_controller_name_.c_str(), operating_controller_name_.c_str());

  if (!wait_for_controller_loaded(ready_controller_name_, autorecovery_timeout_)) {
    RCLCPP_ERROR(this->get_logger(), "Autorecovery: ready controller '%s' was not loaded in time",
                 ready_controller_name_.c_str());
    return false;
  }

  std::lock_guard<std::mutex> lock(state_mutex_);

  if (!switch_controllers({ready_controller_name_}, {operating_controller_name_}, false)) {
    RCLCPP_ERROR(this->get_logger(), "Autorecovery failed: could not activate ready controller");
    return false;
  }

  current_state_ = CoordinatorState::READY;
  publish_state();
  RCLCPP_INFO(this->get_logger(), "Autorecovery succeeded: back in READY state");
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
  request->timeout = rclcpp::Duration(kSwitchControllerHardwareTimeout);

  auto future = switch_controller_client_->async_send_request(request);

  // Wait at least as long as the server-side hardware timeout embedded above, plus a margin, so we
  // don't declare a timeout for a request the server is still legitimately working on.
  auto client_wait_timeout =
      std::max(service_timeout_, kSwitchControllerHardwareTimeout + kSwitchControllerResponseMargin);
  if (future.wait_for(client_wait_timeout) != std::future_status::ready) {
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

bool FrankaControllerCoordinator::is_controller_loaded(const std::string& controller_name,
                                                         std::chrono::milliseconds timeout) {
  auto request = std::make_shared<controller_manager_msgs::srv::ListControllers::Request>();
  auto future = list_controllers_client_->async_send_request(request);

  if (future.wait_for(timeout) != std::future_status::ready) {
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

bool FrankaControllerCoordinator::wait_for_controller_loaded(
    const std::string& controller_name, std::chrono::milliseconds total_timeout) {
  RCLCPP_INFO(this->get_logger(), "Waiting for controller '%s' to be loaded...", controller_name.c_str());
  // Use a short per-call timeout so multiple retries fit within the total budget.
  auto deadline = std::chrono::steady_clock::now() + total_timeout;
  while (std::chrono::steady_clock::now() < deadline) {
    if (is_controller_loaded(controller_name, kControllerLoadPerCallTimeout)) {
      RCLCPP_INFO(this->get_logger(), "Controller '%s' is loaded", controller_name.c_str());
      return true;
    }
    std::this_thread::sleep_for(kControllerLoadPollInterval);
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

void FrankaControllerCoordinator::monitor_autorecovery_cycle() {
  if (std::chrono::steady_clock::now() - *autorecovery_started_ > autorecovery_timeout_) {
    RCLCPP_ERROR(this->get_logger(),
                 "Autorecovery timed out after %ld ms, transitioning to IDLE",
                 autorecovery_timeout_.count());
    transition_to_idle();
    return;
  }
  if (std::chrono::steady_clock::now() < autorecovery_retry_not_before_) {
    return;  // Still cooling down from a previous failed attempt.
  }
  if (!is_controller_manager_available()) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
                         "Autorecovery: waiting for controller manager to become available...");
    return;
  }
  RCLCPP_INFO(this->get_logger(),
              "Autorecovery: controller manager is available, attempting recovery");

  // The staleness check only guesses that a reflex occurred, while the franka_hardware_interface
  // may still be blocked handling it. We need to wait until the hardware interface actually
  // reports inactive before continuing autorecovery.
  if (autorecovery_pending_hardware_deactivation_) {
    if (is_hardware_interface_active()) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
                           "Autorecovery: waiting for hardware interface to report inactive "
                           "before proceeding...");
      return;
    }
    autorecovery_pending_hardware_deactivation_ = false;
  }

  RCLCPP_INFO(this->get_logger(),
              "Autorecovery: Clearing robot error ...");

  if (!clear_robot_error()) {
    RCLCPP_WARN(this->get_logger(),
                "Autorecovery: failed to clear robot error, will retry on next monitor cycle");
    autorecovery_retry_not_before_ = std::chrono::steady_clock::now() + kAutorecoveryRetryBackoff;
    return;
  }

  RCLCPP_INFO(this->get_logger(),
              "Autorecovery: Reactivating hardware interface if not active ...");

  if (!reactivate_hardware_interface()) {
    RCLCPP_WARN(this->get_logger(),
                "Autorecovery: failed to reactivate hardware interface, will retry on next monitor cycle");
    autorecovery_retry_not_before_ = std::chrono::steady_clock::now() + kAutorecoveryRetryBackoff;
    return;
  }

  RCLCPP_INFO(this->get_logger(), "Autorecovery: hardware interface is active, attempting to recover");

  if (!transition_autorecovery_to_ready()) {
    RCLCPP_WARN(this->get_logger(), "Autorecovery: attempt failed, will retry on next monitor cycle");
    autorecovery_retry_not_before_ = std::chrono::steady_clock::now() + kAutorecoveryRetryBackoff;
  }
}

static bool ends_with_franka_hardware_interface(const std::string& name) {
  static constexpr std::string_view kSuffix = "FrankaHardwareInterface";
  return name.size() >= kSuffix.size() &&
         name.compare(name.size() - kSuffix.size(), kSuffix.size(), kSuffix) == 0;
}

bool FrankaControllerCoordinator::clear_robot_error() {
  if (!error_recovery_client_->wait_for_action_server(service_timeout_)) {
    RCLCPP_ERROR(this->get_logger(),
                 "clear_robot_error: error recovery action server not available");
    return false;
  }

  auto goal = franka_msgs::action::ErrorRecovery::Goal();
  auto goal_future = error_recovery_client_->async_send_goal(goal);

  if (goal_future.wait_for(service_timeout_) != std::future_status::ready) {
    RCLCPP_ERROR(this->get_logger(),
                 "clear_robot_error: timed out waiting for goal acceptance");
    return false;
  }

  auto goal_handle = goal_future.get();
  if (!goal_handle) {
    RCLCPP_ERROR(this->get_logger(),
                 "clear_robot_error: goal was rejected by the action server");
    return false;
  }

  auto result_future = error_recovery_client_->async_get_result(goal_handle);
  if (result_future.wait_for(service_timeout_) != std::future_status::ready) {
    RCLCPP_ERROR(this->get_logger(),
                 "clear_robot_error: timed out waiting for result");
    return false;
  }

  auto wrapped_result = result_future.get();
  if (wrapped_result.code != rclcpp_action::ResultCode::SUCCEEDED) {
    RCLCPP_ERROR(this->get_logger(),
                 "clear_robot_error: action did not succeed (code: %d)",
                 static_cast<int>(wrapped_result.code));
    return false;
  }

  RCLCPP_INFO(this->get_logger(), "clear_robot_error: robot error cleared successfully");
  return true;
}

bool FrankaControllerCoordinator::is_hardware_interface_active(std::chrono::milliseconds probe_timeout) {
  auto request =
      std::make_shared<controller_manager_msgs::srv::ListHardwareComponents::Request>();
  auto future = list_hardware_components_client_->async_send_request(request);

  if (future.wait_for(probe_timeout) != std::future_status::ready) {
    RCLCPP_WARN(this->get_logger(),
                "list_hardware_components service call timed out, assuming interface inactive");
    return false;
  }

  auto result = future.get();
  for (const auto& component : result->component) {
    if (ends_with_franka_hardware_interface(component.name) &&
        component.state.id != lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
      RCLCPP_DEBUG(this->get_logger(), "Hardware component '%s' is not active (state id: %u)",
                   component.name.c_str(), component.state.id);
      return false;
    }
  }
  return true;
}

bool FrankaControllerCoordinator::reactivate_hardware_interface(std::chrono::milliseconds probe_timeout) {
  auto list_request =
      std::make_shared<controller_manager_msgs::srv::ListHardwareComponents::Request>();
  auto list_future = list_hardware_components_client_->async_send_request(list_request);

  if (list_future.wait_for(probe_timeout) != std::future_status::ready) {
    RCLCPP_ERROR(this->get_logger(),
                 "list_hardware_components service call timed out during reactivation");
    return false;
  }

  bool all_ok = true;
  auto list_result = list_future.get();
  for (const auto& component : list_result->component) {
    if (!ends_with_franka_hardware_interface(component.name) ||
        component.state.id == lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
      continue;
    }

    RCLCPP_INFO(this->get_logger(), "Reactivating hardware component '%s'",
                component.name.c_str());

    auto set_request =
        std::make_shared<controller_manager_msgs::srv::SetHardwareComponentState::Request>();
    set_request->name = component.name;
    set_request->target_state.id = lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE;
    set_request->target_state.label = "active";

    auto set_future = set_hardware_component_state_client_->async_send_request(set_request);

    if (set_future.wait_for(service_timeout_) != std::future_status::ready) {
      RCLCPP_ERROR(this->get_logger(),
                   "set_hardware_component_state service call timed out for '%s'",
                   component.name.c_str());
      all_ok = false;
      continue;
    }

    if (!set_future.get()->ok) {
      RCLCPP_ERROR(this->get_logger(),
                   "set_hardware_component_state failed for hardware component '%s'",
                   component.name.c_str());
      all_ok = false;
      continue;
    }

    RCLCPP_INFO(this->get_logger(), "Hardware component '%s' successfully reactivated",
                component.name.c_str());
  }
  return all_ok;
}

void FrankaControllerCoordinator::check_robot_state_staleness() {
  CoordinatorState state;
  {
    std::unique_lock<std::mutex> lock(state_mutex_, std::try_to_lock);
    if (!lock.owns_lock()) {
      return;
    }
    state = current_state_;
  }

  if (state != CoordinatorState::READY && state != CoordinatorState::SYNCING &&
      state != CoordinatorState::FOLLOWING) {
    return;
  }

  int64_t last_ns = last_robot_state_ns_.load(std::memory_order_relaxed);
  if (last_ns == 0) {
    return;  // Grace period — no message received yet since the last (re)activation.
  }

  int64_t now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
  auto elapsed = std::chrono::nanoseconds(now_ns - last_ns);
  if (elapsed <= robot_state_stale_timeout_ms_) {
    return;
  }

  std::lock_guard<std::mutex> lock(state_mutex_);
  if (current_state_ != state) {
    return;
  }
  RCLCPP_WARN(this->get_logger(),
              "No robot_state update for over %ld ms, assuming reflex (workaround for known "
              "libfranka/franka_ros2 read() blocking bug), entering AUTORECOVERY (from %s)",
              robot_state_stale_timeout_ms_.count(), to_string(state).c_str());
  autorecovery_started_ = std::chrono::steady_clock::now();
  autorecovery_retry_not_before_ = std::chrono::steady_clock::time_point{};
  autorecovery_pending_hardware_deactivation_ = true;
  current_state_ = CoordinatorState::AUTORECOVERY;
  last_robot_state_ns_.store(0, std::memory_order_relaxed);
  publish_state();
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

  // We might be in AUTORECOVERY already due to a Controller Manager unavailability detected in the
  // previous cycle. Check if we can recover or if we should time out and drop to IDLE.
  if (state == CoordinatorState::AUTORECOVERY) {
    monitor_autorecovery_cycle();
    return;
  }

  // When the Controller Manager becomes unavailable or the hardware interface deactivates, enter
  // AUTORECOVERY. Note: a reflex is detected faster via on_robot_state_received(); this check is a
  // fallback for other causes of hardware deactivation (e.g. controller manager restart).
  if (!is_controller_manager_available() || !is_hardware_interface_active()) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    if (current_state_ != state) {
      return;
    }
    RCLCPP_WARN(this->get_logger(),
                "Controller manager unavailable or hardware interface inactive, entering AUTORECOVERY (from %s)",
                to_string(state).c_str());
    autorecovery_started_ = std::chrono::steady_clock::now();
    autorecovery_retry_not_before_ = std::chrono::steady_clock::time_point{};
    autorecovery_pending_hardware_deactivation_ = false;
    current_state_ = CoordinatorState::AUTORECOVERY;
    last_robot_state_ns_.store(0, std::memory_order_relaxed);
    publish_state();
    return;
  }

  // Active controller health check
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

  // When the Controller is not active but the Controller Manager is available we enter
  // AUTORECOVERY and attempt to recover to READY or fall back to IDLE if that fails.
  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    if (current_state_ != state) {
      return;
    }
    RCLCPP_WARN(this->get_logger(),
                "Controller '%s' is not active, entering AUTORECOVERY (from %s)",
                controller_to_check.c_str(), to_string(state).c_str());
    autorecovery_started_ = std::chrono::steady_clock::now();
    autorecovery_retry_not_before_ = std::chrono::steady_clock::time_point{};
    autorecovery_pending_hardware_deactivation_ = false;
    current_state_ = CoordinatorState::AUTORECOVERY;
    last_robot_state_ns_.store(0, std::memory_order_relaxed);
    publish_state();
  }

  if (!transition_autorecovery_to_ready()) {
    RCLCPP_ERROR(this->get_logger(), "Autorecovery failed, transitioning to IDLE");
    transition_to_idle();
  }
}

}  // namespace controller_coordinator
