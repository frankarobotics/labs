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

source /workspace/src/install/setup.bash
echo "source /workspace/src/install/setup.bash" >>~/.bashrc

# Copy config file to the appropriate location before running this script so that ros2 launch command can find it.
# Note that yml is also renamed to yaml
cp config_controller_coordinator.yml /workspace/src/install/controller_coordinator/share/controller_coordinator/config/config_controller_coordinator.yaml

# For debugging
# sleep infinity

ros2 launch controller_coordinator controller_coordinator.launch.py config_file:=config_controller_coordinator.yaml
