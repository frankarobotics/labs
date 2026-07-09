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

# For debugging
# sleep infinity

uv run --no-sync src/main.py --ros-args --log-level rmw_cyclonedds_cpp:=ERROR
