####################################################################################################
# Stage: deps
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} as uv
FROM ros:jazzy-ros-base AS deps

COPY --from=uv /uv /usr/local/bin/uv

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    clang-14 \
    python3-pip \
    ros-jazzy-ament-cmake \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:${PYTHONPATH}"

# Set Python environment variable to flush logs
ENV PYTHONUNBUFFERED=1

# librealsense: Builder dependencies installation
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    libgl1-mesa-dev \
    libglfw3-dev \
    libglu1-mesa-dev \
    libgtk-3-dev \
    libssl-dev \
    libusb-1.0-0-dev \
    pkg-config \
    && sudo apt-get clean \
    && sudo rm -rf /var/lib/apt/lists/*

# librealsense: This is the version that is being used in the official librealsense/librealsense docker image
# https://hub.docker.com/r/librealsense/librealsense/tags
ENV LIBRS_VERSION=2.58.2
RUN cd /usr/src \
    && curl "https://codeload.github.com/realsenseai/librealsense/tar.gz/refs/tags/v${LIBRS_VERSION}" -o /usr/src/librealsense.tar.gz \
    && tar -zxf /usr/src/librealsense.tar.gz \
    && rm /usr/src/librealsense.tar.gz
RUN ln -s /usr/src/librealsense-${LIBRS_VERSION} /usr/src/librealsense

# librealsense: Build and install
RUN cd /usr/src/librealsense \
    && mkdir build && cd build \
    && cmake \
    -DCMAKE_C_FLAGS_RELEASE="${CMAKE_C_FLAGS_RELEASE} -s" \
    -DCMAKE_CXX_FLAGS_RELEASE="${CMAKE_CXX_FLAGS_RELEASE} -s" \
    -DCMAKE_INSTALL_PREFIX=/opt/librealsense \
    -DBUILD_GRAPHICAL_EXAMPLES=OFF \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_PYTHON_BINDINGS=OFF \
    -DCMAKE_BUILD_TYPE=Release ../ \
    && make -j$(($(nproc)-1)) all \
    && make install

RUN mkdir -p /usr/local/ && mkdir -p /etc/udev/rules.d/
RUN cp -R /opt/librealsense/* /usr/local/
RUN cp -R /usr/src/librealsense/config/99-realsense-libusb.rules /etc/udev/rules.d/
RUN echo "export PYTHONPATH=$PYTHONPATH:/usr/local/lib" >> ~/.bashrc

# librealsense: Install dep packages
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    libusb-1.0-0 \
    software-properties-common \
    udev \
    && sudo apt-get clean \
    && sudo rm -rf /var/lib/apt/lists/*

# librealsense: Install librealsense ros package
RUN sudo apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ros-jazzy-realsense2-* \
    ros-jazzy-image-transport \
    ros-jazzy-image-transport-plugins \
    ros-jazzy-compressed-image-transport \
    ros-jazzy-image-proc \
    ros-jazzy-rosbag2 \
    && sudo apt-get clean \
    && sudo rm -rf /var/lib/apt/lists/*

# Install cyclone dds for ros2 and tuning performance
# https://www.stereolabs.com/docs/ros2/150_dds_and_network_tuning
RUN sudo apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-pip \
    ros-jazzy-rmw-cyclonedds-cpp \
    && sudo apt-get clean \
    && sudo rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

# Set environment variables for protobuf compatibility
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

####################################################################################################
# Stage: dev
FROM deps AS dev

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy the necessary files
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen

# Copy the necessary files
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
    de.franka.image.title="Realsense Camera" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="realsense-camera"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

ENV PYTHONPATH="/workspace/src"
CMD ["/bin/bash", "./entrypoint.sh"]

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

# Copy the necessary files
COPY uv.lock uv.lock
COPY pyproject.toml pyproject.toml

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the necessary files
COPY src src
COPY entrypoint.sh entrypoint.sh

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Add envs and labels at the end to avoid invalidating the docker cache earlier
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Realsense Camera" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="realsense-camera"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

ENV PYTHONPATH="/workspace/src"
CMD ["./entrypoint.sh"]
