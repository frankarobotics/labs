#!/bin/bash

set -eo pipefail

# One worker process: the job store's file lock admits a single owner
exec uv run --no-sync uvicorn main:app \
    --host "${NOMADIC_EPISODE_ANNOTATOR_HOST:?}" \
    --port "${NOMADIC_EPISODE_ANNOTATOR_PORT:?}"
