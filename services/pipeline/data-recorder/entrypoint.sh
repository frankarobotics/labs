#!/bin/bash

# set -euo pipefail

# Tuning DDS for large messages
sudo sysctl -w net.core.rmem_max=2147483647
sudo sysctl -w net.ipv4.ipfrag_high_thresh=134217728
sudo sysctl -w net.ipv4.ipfrag_time=3

source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >>~/.bashrc

# For debugging
# sleep infinity

uv run src/main.py --ros-args --log-level rmw_cyclonedds_cpp:=ERROR
