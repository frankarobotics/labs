#!/bin/bash

# set -euo pipefail

# Tuning DDS for large messages
sudo sysctl -w net.core.rmem_max=2147483647
sudo sysctl -w net.ipv4.ipfrag_high_thresh=134217728
sudo sysctl -w net.ipv4.ipfrag_time=3

# Print ROS environment variables in interactive shells
echo "echo ROS_DOMAIN_ID: \$ROS_DOMAIN_ID" >>~/.bashrc
echo "echo RMW_IMPLEMENTATION: \$RMW_IMPLEMENTATION" >>~/.bashrc
echo "echo CYCLONEDDS_URI: \$CYCLONEDDS_URI" >>~/.bashrc

source /opt/ros/humble/setup.bash
echo "source /opt/ros/humble/setup.bash" >>~/.bashrc

source /workspace/src/install/setup.bash
echo "source /workspace/src/install/setup.bash" >>~/.bashrc

# Copy config file to the appropriate location before running this script so that ros2 launch command can find it.
# Note that yml is also renamed to yaml
cp -v /workspace/config_robotiq_gripper.yml /workspace/src/install/franka_gripper_manager/share/franka_gripper_manager/config/config_robotiq_gripper.yaml

# For debugging
# sleep infinity

ros2 launch franka_gripper_manager robotiq_gripper_controller_client.launch.py config_file:=config_robotiq_gripper.yaml
