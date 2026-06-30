####################################################################################################
# Stage: base
FROM ros:jazzy-ros-base AS base

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-cyclonedds \
    python3-rosdep \
    git \
    python3-vcstool \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rosdep init || true

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]

# Clone robotiq gripper and import dependencies
ARG ROS2_ROBOTIQ_GRIPPER_COMMIT_HASH="3b6cf8ff9106384e72c23de7d3ba989fb6b41141"
RUN mkdir -p /workspace/src/third_party && \
    cd /workspace/src/third_party && \
    git clone https://github.com/PickNikRobotics/ros2_robotiq_gripper.git && \
    cd ros2_robotiq_gripper && git checkout ${ROS2_ROBOTIQ_GRIPPER_COMMIT_HASH} && cd .. && \
    sed -i 's/kGripperMaxSpeed = 0.150;/kGripperMaxSpeed = 1.0;/g' ros2_robotiq_gripper/robotiq_driver/src/hardware_interface.cpp && \
    vcs import . --input ros2_robotiq_gripper/ros2_robotiq_gripper.rolling.repos

# Install dependencies and build third-party packages
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths /workspace/src/third_party --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* && \
    source /opt/ros/jazzy/setup.bash && \
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
    source /opt/ros/jazzy/setup.bash && \
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
    source /opt/ros/jazzy/setup.bash && \
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
