"""Public interface of the analytics data service.

The service is a pure build-time layer: it emits one versioned static payload.
No server, database or network transport is involved.
"""

from __future__ import annotations

from .api import build_gate2_bundle, build_payload
from .types import ServiceOptions, SourcePaths
from .validate import SCHEMA, ContractError

__all__ = [
    "build_payload",
    "build_gate2_bundle",
    "ServiceOptions",
    "SourcePaths",
    "ContractError",
    "SCHEMA",
]
