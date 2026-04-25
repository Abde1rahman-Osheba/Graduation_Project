"""
PATHS Backend — Health-check response schemas.
"""

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    service: str
    status: str
    details: dict | None = None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str


class FullHealthResponse(BaseModel):
    status: str
    services: list[ServiceHealth]
