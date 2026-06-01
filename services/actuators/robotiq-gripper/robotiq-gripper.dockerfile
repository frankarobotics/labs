####################################################################################################
# Stage: base
FROM ros:humble-ros-base AS base

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-cyclonedds \
    python3-rosdep \
    git \
    python3-vcstool \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rosdep init || true

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]

# Clone robotiq gripper and import dependencies
ARG ROS2_ROBOTIQ_GRIPPER_COMMIT_HASH="2ff85455d4b9f973c4b0bab1ce95fb09367f0d26"
RUN mkdir -p /workspace/src/third_party && \
    cd /workspace/src/third_party && \
    git clone https://github.com/PickNikRobotics/ros2_robotiq_gripper.git && \
    cd ros2_robotiq_gripper && git checkout ${ROS2_ROBOTIQ_GRIPPER_COMMIT_HASH} && cd .. && \
    sed -i 's/kGripperMaxSpeed = 0.150;/kGripperMaxSpeed = 1.0;/g' ros2_robotiq_gripper/robotiq_driver/src/hardware_interface.cpp && \
    vcs import . --input ros2_robotiq_gripper/ros2_robotiq_gripper.humble.repos

# Install dependencies and build third-party packages
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths /workspace/src/third_party --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* && \
    source /opt/ros/humble/setup.bash && \
    cd /workspace/src && \
    colcon build --symlink-install

####################################################################################################
# Stage: dev
FROM base AS dev

# Add development and debugging tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    iputils-ping \
    vim-tiny \
    wget \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build franka_gripper_manager
COPY src/third_party/gello_software/ros2 /workspace/src/third_party/gello_software/ros2
RUN cd /workspace/src/ && \
    source /opt/ros/humble/setup.bash && \
    colcon build --packages-select franka_gripper_manager

COPY entrypoint.sh entrypoint.sh

# Add envs and labels
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Robotiq Gripper" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="robotiq-gripper"
ENV BUILD_CREATED=$BUILD_CREATED \
    BUILD_TARGET=$BUILD_TARGET \
    BUILD_VERSION=$BUILD_VERSION \
    GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]

####################################################################################################
# Stage: prod
FROM base AS prod

# Build franka_gripper_manager
COPY src/third_party/gello_software/ros2 /workspace/src/third_party/gello_software/ros2
RUN cd /workspace/src/ && \
    source /opt/ros/humble/setup.bash && \
    colcon build --packages-select franka_gripper_manager

COPY entrypoint.sh entrypoint.sh

# Add envs and labels
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Robotiq Gripper" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="robotiq-gripper"
ENV BUILD_CREATED=$BUILD_CREATED \
    BUILD_TARGET=$BUILD_TARGET \
    BUILD_VERSION=$BUILD_VERSION \
    GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]
