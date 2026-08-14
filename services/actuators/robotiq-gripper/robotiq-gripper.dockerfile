####################################################################################################
# Stage: base
FROM ros:jazzy-ros-base AS base

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-cyclonedds \
    python3-rosdep \
    git \
    libserialport-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rosdep init || true

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]

# Official Robotiq ROS 2 driver (robotiq/ros, provided as git submodule under src/third_party).
# robotiq_driver's CMake pulls in the gripper SDK via add_subdirectory(../../extern/grippers/sdk_cpp),
# so grippers/ and extern/ must remain siblings here.
# robotiq_tsf and the tactile sensor SDK are excluded (force sensitive fingertips are not supported).
COPY src/third_party/robotiq_ros/grippers /workspace/src/third_party/robotiq_ros/grippers
COPY src/third_party/robotiq_ros/extern/grippers/sdk_cpp /workspace/src/third_party/robotiq_ros/extern/grippers/sdk_cpp
RUN touch /workspace/src/third_party/robotiq_ros/extern/grippers/sdk_cpp/COLCON_IGNORE

# Install dependencies and build the gripper packages (driver, controllers, description).
# robotiq_driver must be listed explicitly: it provides the hardware interface plugin but
# is not a package.xml dependency of the other two, so --packages-up-to would skip it.
# libserialport has no rosdep key and is installed above, hence the skip key.
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths /workspace/src/third_party --ignore-src -r -y --skip-keys libserialport && \
    rm -rf /var/lib/apt/lists/* && \
    source /opt/ros/jazzy/setup.bash && \
    cd /workspace/src && \
    colcon build --symlink-install --packages-up-to robotiq_driver robotiq_controllers robotiq_description

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

# Build robotiq_gripper_bringup
COPY src/robotiq_gripper_bringup /workspace/src/robotiq_gripper_bringup
RUN cd /workspace/src/ && \
    source /opt/ros/jazzy/setup.bash && \
    colcon build --packages-select robotiq_gripper_bringup

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

# Build robotiq_gripper_bringup
COPY src/robotiq_gripper_bringup /workspace/src/robotiq_gripper_bringup
RUN cd /workspace/src/ && \
    source /opt/ros/jazzy/setup.bash && \
    colcon build --packages-select robotiq_gripper_bringup

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
