"""Nomadic episode annotator API."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from handlers.annotations import router
from jobs.service import get_annotation_service


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Own the single annotation worker for the process lifetime."""
    service = get_annotation_service()
    service.start()
    try:
        yield
    finally:
        await asyncio.to_thread(service.close)


app = FastAPI(title="Nomadic Episode Annotator", lifespan=lifespan)
app.include_router(router)
