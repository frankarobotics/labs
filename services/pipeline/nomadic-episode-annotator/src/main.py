"""Nomadic episode annotator API."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from handlers.annotations import router
from jobs.service import get_annotation_service


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Close the worker if a request started it."""
    try:
        yield
    finally:
        if get_annotation_service.cache_info().currsize:
            await asyncio.to_thread(get_annotation_service().close)


app = FastAPI(title="Nomadic Episode Annotator", lifespan=lifespan)
app.include_router(router)
