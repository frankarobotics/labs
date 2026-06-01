# Franka Data Collection UI

A React web interface for controlling robotics data collection operations, providing real-time
device monitoring, teleoperation capabilities and episode management.

## Overview

Franka Data Collection UI provides a web interface built with React 19, React Router 7, TypeScript,
and Tailwind CSS. It enables episode management (create, record, replay, delete), interactive teleoperation, real-time device monitoring, live camera streaming, and task selection.

### Runtime Responsibilities

1. **Server-side rendering**: Express.js server renders React components on the server for fast initial page loads.
2. **API client injection**: Creates typed `openapi-fetch` client per request and injects it via React Router context (`server/app.ts`).
3. **Session management**: Encrypted HTTP-only cookies track the active episode ID, auto-validated against the backend on each request.
4. **Backend proxying**: All API calls route through SSR loaders/actions to the data-collection service (default port 3001).
5. **WebSocket streaming**: Client-side WebSocket connections to data-collection service for live camera feeds.

### Architecture

- **Express.js server** (`server.js`): Entry point with compression, static file serving, and Vite middleware (dev) or pre-built SSR handler (prod).
- **React Router app** (`server/app.ts`): Creates request handler, resolves backend URL, and injects API client into route context.
- **Route loaders/actions** (`app/routes/`): Server-side data fetching and mutations via injected API client.
- **Components** (`app/components/`): Modular UI components for teleoperation, episodes, device status, and camera streaming.
- **Sessions** (`app/sessions/`): Cookie-based episode tracking with backend validation.

### Configuration

All configuration is loaded from `deployments/<station>/config_data_collection.yml` (mounted to `/workspace/config_data_collection.yml`). The `data_collection.url` field determines which port the UI connects to. See [Deployment README](../../../deployments/README.md).

The following environment variables can be set under the `data-collection-ui` service in `docker-compose.dev.yml` if needed:

- `PORT`: Server listen port (default `4000`)
- `NODE_ENV`: `development` enables Vite HMR, `production` serves pre-built assets

### Regenerating API Types

The typed API client uses `app/api/data-collection/types.d.ts`, which is auto-generated from the data-collection service's OpenAPI spec using [openapi-typescript](https://openapi-ts.dev/). To regenerate it after backend API changes:

1. Make sure the `data-collection` and `data-collection-ui` containers are running.
2. Run `openapi-typescript` inside the UI container:

   ```bash
   docker exec data-collection-ui npx openapi-typescript http://localhost:3001/openapi.json -o /app/app/api/data-collection/types.d.ts
   ```

3. Copy the generated file to the host:

   ```bash
   docker cp data-collection-ui:/app/app/api/data-collection/types.d.ts services/pipeline/data-collection-ui/app/api/data-collection/types.d.ts
   ```