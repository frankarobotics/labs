####################################################################################################
# Stage: deps
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} as uv
FROM ros:jazzy-ros-base AS deps

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}"

# Set Python environment variable to flush logs
ENV PYTHONUNBUFFERED=1

# Install cyclone dds for ros2 and tuning performance
# https://www.stereolabs.com/docs/ros2/150_dds_and_network_tuning
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-cv-bridge \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

####################################################################################################
# Stage: dev
FROM deps AS dev

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}"

# Copy the necessary files
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen

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
    de.franka.image.title="Data Collection" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="data-collection"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

ENV PYTHONPATH="/workspace/src"
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

COPY src src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

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
    de.franka.image.title="Data Collection" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="data-collection"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

ENV PYTHONPATH="/workspace/src"
CMD ["./entrypoint.sh"]
