#!/bin/bash

# Tuning DDS for large messages
sudo sysctl -w net.core.rmem_max=2147483647
sudo sysctl -w net.ipv4.ipfrag_high_thresh=134217728
sudo sysctl -w net.ipv4.ipfrag_time=3

# Print ROS environment variables in interactive shells
echo "echo ROS_DOMAIN_ID: \$ROS_DOMAIN_ID" >>~/.bashrc
echo "echo RMW_IMPLEMENTATION: \$RMW_IMPLEMENTATION" >>~/.bashrc
echo "echo CYCLONEDDS_URI: \$CYCLONEDDS_URI" >>~/.bashrc

source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >>~/.bashrc

source /workspace/ros2_ws/install/local_setup.bash >>~/.bashrc
echo "source /workspace/ros2_ws/install/local_setup.bash" >>~/.bashrc

# For debugging
# sleep infinity

# Install the custom launch file
mkdir -p /workspace/ros2_ws/install/zed_wrapper/share/zed_wrapper/launch
cp -v /workspace/src/zed.launch.py /workspace/ros2_ws/install/zed_wrapper/share/zed_wrapper/launch/

# Start the cameras
ros2 launch zed_wrapper zed.launch.py
