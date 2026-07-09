####################################################################################################
# Stage: base
FROM ros:jazzy-ros-base AS base

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-cyclonedds \
    python3-rosdep \
    git \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rosdep init || true

WORKDIR /workspace

SHELL ["/bin/bash", "-c"]

RUN mkdir -p /workspace/src/third_party && \
    cd /workspace/src/third_party && \
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/frankaemika/franka_ros2.git -b v3.4.0 && \
    cd franka_ros2 && \
    git sparse-checkout set franka_msgs

RUN source /opt/ros/jazzy/setup.bash && \
    cd /workspace/src && \
    colcon build --packages-select franka_msgs --cmake-args -DCMAKE_BUILD_TYPE=Release

####################################################################################################
# Stage: dev
FROM base AS dev

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    iputils-ping \
    vim-tiny \
    wget \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]
COPY src/controller_coordinator/package.xml src/controller_coordinator/package.xml

# Install dependencies and build
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* 

COPY src src

RUN cd /workspace/src && \
    source /opt/ros/jazzy/setup.bash && \
    source /workspace/src/install/setup.bash && \
    colcon build --packages-select controller_coordinator

COPY entrypoint.sh entrypoint.sh

ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Controller Coordinator" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="controller-coordinator"
ENV BUILD_CREATED=$BUILD_CREATED \
    BUILD_TARGET=$BUILD_TARGET \
    BUILD_VERSION=$BUILD_VERSION \
    GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]

####################################################################################################
# Stage: prod
FROM base AS prod

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]
COPY src src

# Install dependencies and build
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* && \
    cd /workspace/src && \
    source /opt/ros/jazzy/setup.bash && \
    source /workspace/src/install/setup.bash && \
    colcon build --packages-select controller_coordinator

COPY entrypoint.sh entrypoint.sh

ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Controller Coordinator" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="controller-coordinator"
ENV BUILD_CREATED=$BUILD_CREATED \
    BUILD_TARGET=$BUILD_TARGET \
    BUILD_VERSION=$BUILD_VERSION \
    GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]
