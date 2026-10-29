# Nomadic Episode Annotator

Optional service that sends one saved LABS episode at a time to Nomadic for action annotation, on an operator's request.
Stations without it run unchanged.

## Interface

- HTTP on port `3005`, under `/api/v1/episodes/{episode_id}/annotations`.
- Reads processed episodes from `/workspace/data/processed_episodes` (read-only).
- Keeps job state in `/workspace/data/nomadic_annotations` (read-write).
- Configured through `NOMADIC_*` environment variables; see `src/annotations/config.py`.

Runs as a single process because the job store admits one worker. See the [setup guide](docs/nomadic-annotations.md).

## Development

```sh
uv run --frozen pytest
```
