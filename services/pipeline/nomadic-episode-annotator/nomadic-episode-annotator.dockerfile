####################################################################################################
# Stage: deps
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM python:3.12-slim AS deps

COPY --from=uv /uv /usr/local/bin/uv

# Set Python environment variable to flush logs
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

ENV PYTHONPATH="/workspace/src"

####################################################################################################
# Stage: dev
FROM deps AS dev

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# target /packages so the pyproject path sources "../packages/<name>" resolve from /workspace
COPY --from=packages pipeline-configs /packages/pipeline-configs
COPY --from=packages pipeline-episodes /packages/pipeline-episodes

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen

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
    de.franka.image.title="Nomadic Episode Annotator" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="nomadic-episode-annotator"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]

####################################################################################################
# Stage: prod
# https://github.com/astral-sh/uv-docker-example/blob/main/Dockerfile
FROM deps AS prod

ENV UV_COMPILE_BYTECODE=1

# target /packages so the pyproject path sources "../packages/<name>" resolve from /workspace
COPY --from=packages pipeline-configs /packages/pipeline-configs
COPY --from=packages pipeline-episodes /packages/pipeline-episodes

COPY uv.lock uv.lock
COPY pyproject.toml pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

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
    de.franka.image.title="Nomadic Episode Annotator" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="nomadic-episode-annotator"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

CMD ["./entrypoint.sh"]
