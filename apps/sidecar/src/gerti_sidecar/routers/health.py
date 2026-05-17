"""Endpoint /v1/health — liveness + ambient info."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gerti_sidecar import __version__
from gerti_sidecar.config import Settings, get_settings

router = APIRouter(prefix="/health", tags=["meta"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str


@router.get("", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=__version__,
    )
