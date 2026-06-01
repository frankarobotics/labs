##########################################################################################
# Install development dependencies
FROM node:22 AS development-dependencies-env
COPY . /workspace
WORKDIR /workspace
RUN npm ci

##########################################################################################
# Install production dependencies
FROM node:22 AS production-dependencies-env
COPY ./package.json package-lock.json /workspace/
WORKDIR /workspace
RUN npm ci --omit=dev

##########################################################################################
# Build application
FROM node:22 AS build-env
COPY . /workspace/
COPY --from=development-dependencies-env /workspace/node_modules /workspace/node_modules
WORKDIR /workspace
RUN npm run build

##########################################################################################
# Run development server
FROM node:22 AS dev

WORKDIR /workspace

# Copy lockfile first for reproducible layer
COPY package.json package-lock.json ./
RUN npm ci

COPY react-router.config.ts vite.config.ts entrypoint.sh /workspace/
COPY server.js ./
COPY public/ ./public/
COPY server/ ./server/
COPY app/ ./app/

ENV NODE_ENV="development"

# Add envs and labels at the end to avoid invalidating the docker cache
ARG BUILD_CREATED \
  BUILD_TARGET \
  BUILD_VERSION \
  GIT_COMMIT
LABEL \
  image.build-target=$BUILD_TARGET \
  image.created=$BUILD_CREATED \
  image.git-commit=$GIT_COMMIT \
  image.title="Franka Data Collection UI" \
  image.version=$BUILD_VERSION \
  service.name="data-collection-ui"
ENV BUILD_CREATED=$BUILD_CREATED \
  BUILD_TARGET=$BUILD_TARGET \
  BUILD_VERSION=$BUILD_VERSION \
  GIT_COMMIT=$GIT_COMMIT

ENTRYPOINT ["./entrypoint.sh"]

##########################################################################################
# Run production server
FROM node:22 AS prod
COPY ./package.json package-lock.json server.js entrypoint.sh /workspace/
COPY --from=build-env /workspace/dist /workspace/dist
COPY --from=production-dependencies-env /workspace/node_modules /workspace/node_modules
WORKDIR /workspace

ENV NODE_ENV="production"

# Add envs and labels at the end to avoid invalidating the docker cache
ARG BUILD_CREATED \
  BUILD_TARGET \
  BUILD_VERSION \
  GIT_COMMIT
LABEL \
  image.build-target=$BUILD_TARGET \
  image.created=$BUILD_CREATED \
  image.git-commit=$GIT_COMMIT \
  image.title="Franka Data Collection UI" \
  image.version=$BUILD_VERSION \
  service.name="data-collection-ui"
ENV BUILD_CREATED=$BUILD_CREATED \
  BUILD_TARGET=$BUILD_TARGET \
  BUILD_VERSION=$BUILD_VERSION \
  GIT_COMMIT=$GIT_COMMIT

ENTRYPOINT ["./entrypoint.sh"]
