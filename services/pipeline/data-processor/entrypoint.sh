#!/bin/bash

set -eo pipefail

source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >>~/.bashrc

# For debugging
# sleep infinity

uv run src/main.py
