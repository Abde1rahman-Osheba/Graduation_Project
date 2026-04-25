"""
PATHS Backend — Job Source Base Adapter.
"""
from typing import Protocol, runtime_checkable

@runtime_checkable
class BaseJobSourceAdapter(Protocol):
    name: str
    source_type: str

    async def discover(self, query: dict | None = None) -> list[str]:
        """
        Discover job URLs. Returns a list of target strings (e.g. URLs).
        """
        ...

    async def fetch(self, target: str) -> dict:
        """
        Fetch a specific target and return raw payload.
        """
        ...

    async def parse(self, raw: dict) -> list[dict]:
        """
        Parse raw payload into semi-structured dictionaries.
        """
        ...
