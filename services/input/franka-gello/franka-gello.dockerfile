####################################################################################################
# Stage: deps
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} as uv
FROM ros:humble-ros-base AS deps

COPY --from=uv /uv /usr/local/bin/uv

# Set Python environment variable to flush logs
ENV PYTHONUNBUFFERED=1

# Install cyclone dds for ros2 and tuning performance
# https://www.stereolabs.com/docs/ros2/150_dds_and_network_tuning
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-cv-bridge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# https://github.com/wuphilipp/gello_software/blob/main/ros2/.devcontainer/Dockerfile
RUN apt-get update && apt-get install -y \
  # Install libfranka build depencencies
  build-essential \
  cmake \
  lsof \
  psmisc \
  git \
  libeigen3-dev \
  libfmt-dev \
  libpoco-dev \
  ros-humble-pinocchio \
  # Install ros packages
  ros-humble-rqt-common-plugins \
  python3-colcon-common-extensions \
  python3-colcon-mixin \
  python3-pip \
  python3-vcstool \
  && rm -rf /var/lib/apt/lists/*

####################################################################################################
# Stage: dev
FROM deps AS dev

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH}:/workspace/src"

# Copy the necessary files
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

# Install the project's dependencies using the lockfile and settings in the system python
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export -o requirements.txt && \
    uv pip sync requirements.txt --system

# Build franka_gello_state_publisher
SHELL ["/bin/bash", "-c"]
COPY src/third_party src/third_party
RUN cd /workspace/src/third_party/gello_software/ros2 && \
    source /opt/ros/humble/setup.bash && \
    colcon build --packages-select franka_gello_state_publisher

COPY src src
COPY entrypoint.sh entrypoint.sh

# Add envs and labels at the end to avoid invalidating the docker cache earlier
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Franka GELLO" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="franka-gello"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]

####################################################################################################
# Stage: prod
# https://github.com/astral-sh/uv-docker-example/blob/main/Dockerfile
FROM deps AS prod

# Only for debugging
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH}:/workspace/src"

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
# ENV UV_LINK_MODE=copy

# Copy the necessary files
COPY uv.lock uv.lock
COPY pyproject.toml pyproject.toml

# Install the project's dependencies using the lockfile and settings in the system python
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export -o requirements.txt && \
    uv pip sync requirements.txt --system

# Build franka_gello_state_publisher
SHELL ["/bin/bash", "-c"]
COPY src/third_party src/third_party
RUN cd /workspace/src/third_party/gello_software/ros2 && \
    source /opt/ros/humble/setup.bash && \
    colcon build --packages-select franka_gello_state_publisher

COPY src src
COPY entrypoint.sh entrypoint.sh

# Add envs and labels at the end to avoid invalidating the docker cache earlier
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Franka GELLO" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="franka-gello"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]
