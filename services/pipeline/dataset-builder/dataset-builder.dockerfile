####################################################################################################
# Stage: deps
FROM ros:jazzy-ros-base AS deps

ENV UV_VERSION=0.8.22
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | UV_INSTALL_DIR=/usr/local/bin sh
RUN if ! command -v uv >/dev/null 2>&1; then echo "uv not installed in /usr/local/bin" >&2; exit 1; fi && uv --version

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:ubuntuhandbook1/ffmpeg7 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg \
    ros-jazzy-cv-bridge \
    ros-jazzy-ros-base \
    ros-jazzy-ros2bag \
    ros-jazzy-rosbag2-transport \
    ros-jazzy-rosbag2-storage-mcap \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

####################################################################################################
# Stage: dev
FROM deps AS dev

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping tree vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:/workspace/src"

# target /packages so the pyproject path source "../packages/pipeline-configs" resolves from /workspace
COPY --from=packages pipeline-configs /packages/pipeline-configs

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen

RUN --mount=type=cache,target=/root/.cache/uv \
    uv add "cmake<4.0" lerobot==0.3.3

COPY src src
COPY entrypoint.sh entrypoint.sh

ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Dataset Builder" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="dataset-builder"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]

####################################################################################################
# Stage: prod
FROM deps AS prod

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONPATH="/opt/ros/jazzy/lib/python3.12/site-packages:/workspace/src"
ENV UV_COMPILE_BYTECODE=1

# target /packages so the pyproject path source "../packages/pipeline-configs" resolves from /workspace
COPY --from=packages pipeline-configs /packages/pipeline-configs

COPY uv.lock uv.lock
COPY pyproject.toml pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv add "cmake<4.0" lerobot==0.3.3

COPY src src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY entrypoint.sh entrypoint.sh

ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Dataset Builder" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="dataset-builder"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]