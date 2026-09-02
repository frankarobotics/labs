####################################################################################################
# Stage: deps
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} as uv
FROM ros:jazzy-ros-base AS deps

COPY --from=uv /uv /usr/local/bin/uv

# Set Python environment variable to flush logs
ENV PYTHONUNBUFFERED=1

# Install cyclone dds for ros2 and tuning performance
# https://www.stereolabs.com/docs/ros2/150_dds_and_network_tuning
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
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

# Clone and build franka_ros2 and its dependencies 
RUN mkdir -p /workspace/src/third_party && \
    cd /workspace/src/third_party && \
    git clone https://github.com/frankaemika/franka_ros2.git -b v3.5.3 && \
    vcs import < franka_ros2/dependency.repos && \
    find . -name ".git" -type d -execdir git submodule update --init --recursive \;

# Install dependencies and build third-party packages 
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths /workspace/src/third_party --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* && \
    source /opt/ros/jazzy/setup.bash && \
    cd /workspace/src && \
    colcon build --symlink-install --packages-skip franka_follower_controllers --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF

####################################################################################################
# Stage: dev
FROM deps AS dev

# Add development and debugging tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    iputils-ping \
    vim-tiny \
    wget \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY src/third_party/franka_follower_controllers /workspace/src/third_party/franka_follower_controllers

RUN source /opt/ros/jazzy/setup.bash && \
    source /workspace/src/install/setup.bash && \
    cd /workspace/src && \
    colcon build --symlink-install --packages-select franka_follower_controllers --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF

COPY entrypoint.sh entrypoint.sh

ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Franka Robot Follower" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="franka-robot"
ENV BUILD_CREATED=$BUILD_CREATED \
    BUILD_TARGET=$BUILD_TARGET \
    BUILD_VERSION=$BUILD_VERSION \
    GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]

####################################################################################################
# Stage: prod
FROM deps AS prod

COPY src/third_party/franka_follower_controllers /workspace/src/third_party/franka_follower_controllers

RUN source /opt/ros/jazzy/setup.bash && \
    source /workspace/src/install/setup.bash && \
    cd /workspace/src && \
    colcon build --packages-select franka_follower_controllers --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF

COPY entrypoint.sh entrypoint.sh

ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Franka Robot Follower" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="franka-robot"
ENV BUILD_CREATED=$BUILD_CREATED \
    BUILD_TARGET=$BUILD_TARGET \
    BUILD_VERSION=$BUILD_VERSION \
    GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]
