#!/bin/bash

set -eo pipefail

# One worker process: the job store's file lock admits a single owner
exec uv run --no-sync uvicorn main:app --host 0.0.0.0 --port 3005
