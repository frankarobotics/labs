#!/bin/bash

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

echo "echo ROS_DOMAIN_ID: \$ROS_DOMAIN_ID" >>~/.bashrc

# Install the custom launch file
mkdir -p /opt/ros/humble/share/realsense2_camera/launch
cp -v /workspace/src/realsense.launch.py /opt/ros/humble/share/realsense2_camera/launch/

# Config file location
CONFIG_FILE=${CONFIG_FILE:-/workspace/config_realsense_camera.yml}

# For debugging
# sleep infinity

ros2 launch realsense2_camera realsense.launch.py config_file:=${CONFIG_FILE}
