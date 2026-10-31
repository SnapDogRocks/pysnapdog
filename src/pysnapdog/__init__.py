# SPDX-License-Identifier: Apache-2.0
"""Async Python client for the SnapDog multi-room audio server."""

from .client import DEFAULT_PORT, SnapDogClient
from .exceptions import (
    SnapDogAuthError,
    SnapDogConnectionError,
    SnapDogError,
    SnapDogResponseError,
)
from .models import SystemStatus, VersionInfo, Zone

__all__ = [
    "DEFAULT_PORT",
    "SnapDogAuthError",
    "SnapDogClient",
    "SnapDogConnectionError",
    "SnapDogError",
    "SnapDogResponseError",
    "SystemStatus",
    "VersionInfo",
    "Zone",
]
