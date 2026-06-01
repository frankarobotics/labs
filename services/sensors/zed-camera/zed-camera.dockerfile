####################################################################################################
# Stage: deps
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} as uv
FROM stereolabs/zed:5.0-devel-cuda12.8-ubuntu24.04 AS deps

# Install uv
COPY --from=uv /uv /usr/local/bin/uv

COPY ros-archive-keyring.gpg /usr/share/keyrings/ros-archive-keyring.gpg
RUN echo "deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/ros2.list

# Install ROS 2 Jazzy + required tools
RUN apt-get update && apt-get install -y \
    curl gnupg2 lsb-release locales git && \
    locale-gen en_US en_US.UTF-8 && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 && \
    export LANG=en_US.UTF-8 && \
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | apt-key add - && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | \
    tee /etc/apt/sources.list.d/ros2.list && \
    apt-get update && \
    apt-get install -y ros-jazzy-ros-base python3-rosdep python3-colcon-common-extensions && \
    rosdep init && rosdep update && \
    rm -rf /var/lib/apt/lists/*

# Source ROS 2 in environment
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
SHELL ["/bin/bash", "-c"]
RUN echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-jazzy-ament-cmake-auto \
    ros-jazzy-rmw-cyclonedds-cpp \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create and build ROS 2 workspace with ZED wrapper
ENV ROS_WS=/workspace/ros2_ws
RUN mkdir -p ${ROS_WS}/src
COPY src/third_party/ ${ROS_WS}/src/
RUN cd ${ROS_WS} && \
    source /opt/ros/jazzy/setup.bash && \
    sudo apt update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    colcon build --symlink-install --cmake-args=-DCMAKE_BUILD_TYPE=Release --parallel-workers $(nproc) && \
    echo "source ${ROS_WS}/install/setup.bash" >> ~/.bashrc

####################################################################################################
# Stage: dev
FROM deps AS dev

# Install extra dev tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl iputils-ping vim-tiny wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy the necessary files
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen

# Copy your project files
COPY src src
COPY tests tests
COPY entrypoint.sh entrypoint.sh

# Metadata and environment variables
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="ZED Camera" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="zed-camera"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT
ENV PYTHONPATH="/workspace/src"

CMD ["/bin/bash", "./entrypoint.sh"]

####################################################################################################
# Stage: prod
FROM deps AS prod

# Install extra dev tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl iputils-ping vim-tiny wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
# ENV UV_LINK_MODE=copy

# Copy the necessary files
COPY uv.lock uv.lock
COPY pyproject.toml pyproject.toml

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy your project files
COPY src src
COPY entrypoint.sh entrypoint.sh

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Metadata and environment variables
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="ZED Camera" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="zed-camera"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT
ENV PYTHONPATH="/workspace/src"

CMD ["/bin/bash", "./entrypoint.sh"]
