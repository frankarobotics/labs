#!/bin/bash

set -eo pipefail

source /opt/ros/jazzy/setup.bash
echo "source /opt/ros/jazzy/setup.bash" >>~/.bashrc

uv run src/main.py "$@"
