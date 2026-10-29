"""Composition root wiring the job service to the Nomadic SDK adapter."""

from functools import lru_cache

from adapters.nomadic_gateway import NomadicGateway
from configs.annotator import get_annotation_config
from jobs.service import AnnotationService


@lru_cache
def get_annotation_service() -> AnnotationService:
    """Return this process's optional annotation worker."""
    return AnnotationService(get_annotation_config(), NomadicGateway)
