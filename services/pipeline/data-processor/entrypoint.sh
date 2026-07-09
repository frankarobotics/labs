#!/bin/bash

set -eo pipefail

source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >>~/.bashrc

# For debugging
# sleep infinity

uv run --no-sync src/main.py
