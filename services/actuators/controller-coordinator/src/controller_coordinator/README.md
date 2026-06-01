# Controller Coordinator

ROS2 node that manages robot arm controller state transitions between Idle, Ready, Syncing, and Following modes.

## States

- **Idle**: All controllers inactive
- **Ready**: Ready-state controller active (prepares the robot for the next step in the pipeline by activating a controller such as gravity compensation for manual positioning or a move-to-position controller to reach a specific configuration before proceeding to data collection, inference, etc.)
- **Syncing**: Operating controller active, moving to start position
- **Following**: Operating controller active, following target joint states

The transition from Syncing to Following happens automatically when the operating controller reports that syncing is complete (via its `~/state` topic).

## Launch

```bash
ros2 launch controller_coordinator controller_coordinator.launch.py config_file:=example_fr3_config.yaml
```

## Usage

```bash
# Transition to Ready
ros2 service call /<namespace>/controller_coordinator/get_ready std_srvs/srv/Trigger

# Transition to Operating (Following or SyncingFollowing)
ros2 service call /<namespace>/controller_coordinator/start_operating std_srvs/srv/Trigger

# Transition to Idle
ros2 service call /<namespace>/controller_coordinator/stop std_srvs/srv/Trigger
```

## Configuration

Configure robot namespace, ready controller, and operating controller in your config file:

```yaml
robot1:
  namespace: ''
  ready_controller: 'joint_trajectory_example_controller'
  operating_controller: 'cartesian_pose_example_controller'
```
