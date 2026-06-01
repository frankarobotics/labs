####################################################################################################
# Stage: base
FROM ros:humble-ros-base AS base

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-cyclonedds \
    python3-rosdep \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rosdep init || true

WORKDIR /workspace

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

ENV PYTHONPATH="/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]
COPY src/controller_coordinator/package.xml src/controller_coordinator/package.xml

# Install dependencies and build
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* 

COPY src src

RUN cd /workspace/src && \
    source /opt/ros/humble/setup.bash && \
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

ENV PYTHONPATH="/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH}:/workspace/src"

SHELL ["/bin/bash", "-c"]
COPY src src

# Install dependencies and build
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* && \
    cd /workspace/src && \
    source /opt/ros/humble/setup.bash && \
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
