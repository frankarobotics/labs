
####################################################################################################
# Stage: deps
FROM golang:1.25 AS deps

WORKDIR /workspace

# Install git for go get
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy go mod files and download dependencies
COPY go.mod go.sum ./
RUN go mod download

####################################################################################################
# Stage: builder
FROM deps AS builder

WORKDIR /workspace

COPY go.mod go.sum ./
COPY main.go main.go
COPY migrations migrations
COPY seed seed

# Build the migrate binary
RUN CGO_ENABLED=0 GOOS=linux go build -o migrate main.go

####################################################################################################
# Stage: dev
FROM deps AS dev

WORKDIR /workspace

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY main.go main.go
COPY migrations migrations
COPY seed seed

# Install air for hot reload (optional, comment if not needed)
RUN go install github.com/air-verse/air@v1.62.0

# Add envs and labels at the end to avoid invalidating the docker cache earlier
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Migrate Service" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="migrate"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

# Set default command for dev
CMD ["air"]

####################################################################################################
# Stage: prod
FROM debian:bookworm-slim AS prod

WORKDIR /workspace

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl iputils-ping vim-tiny wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the migrate binary, migrations and seed
COPY --from=builder /workspace/migrate /usr/local/bin/migrate
COPY migrations migrations
COPY seed seed

# Add envs and labels at the end to avoid invalidating the docker cache earlier
ARG BUILD_CREATED
ARG BUILD_TARGET
ARG BUILD_VERSION
ARG GIT_COMMIT
LABEL \
    de.franka.image.build-target=$BUILD_TARGET \
    de.franka.image.created=$BUILD_CREATED \
    de.franka.image.git-commit=$GIT_COMMIT \
    de.franka.image.title="Migrate Service" \
    de.franka.image.version=$BUILD_VERSION \
    de.franka.service.name="migrate"
ENV BUILD_CREATED=$BUILD_CREATED
ENV BUILD_TARGET=$BUILD_TARGET
ENV BUILD_VERSION=$BUILD_VERSION
ENV GIT_COMMIT=$GIT_COMMIT

# Default command runs migrations
ENTRYPOINT ["/usr/local/bin/migrate"]
CMD []
