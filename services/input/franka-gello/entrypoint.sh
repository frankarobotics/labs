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

source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >>~/.bashrc

source src/third_party/gello_software/ros2/install/setup.bash
echo "source src/third_party/gello_software/ros2/install/setup.bash" >>~/.bashrc

# Copy config file to the appropriate location before running this script so that ros2 launch command can find it.
# Note that yml is also renamed to yaml
cp config_gello.yml /workspace/src/third_party/gello_software/ros2/install/franka_gello_state_publisher/share/franka_gello_state_publisher/config/config_gello.yaml

# For debugging
# sleep infinity

ros2 launch franka_gello_state_publisher main.launch.py config_file:=config_gello.yaml
