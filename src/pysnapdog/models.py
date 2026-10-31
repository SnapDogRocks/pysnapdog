# SPDX-License-Identifier: Apache-2.0
"""Typed models of the SnapDog REST API (API version 1).

The field names follow ``openapi.json`` of the server. A response that lacks a
required field raises ``SnapDogResponseError`` instead of producing a half-filled
object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from .exceptions import SnapDogResponseError


def _require(data: dict[str, Any], key: str, kind: type, what: str) -> Any:  # noqa: ANN401
    """Return ``data[key]`` if it is there and of the expected type."""
    value = data.get(key)
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise SnapDogResponseError(f"{what}: field {key!r} is missing or not {kind.__name__}")
    return value


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """``GET /api/v1/system/version``."""

    name: str
    version: str
    rust_version: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build the model from a decoded JSON object."""
        return cls(
            name=_require(data, "name", str, "VersionInfo"),
            version=_require(data, "version", str, "VersionInfo"),
            rust_version=_require(data, "rust_version", str, "VersionInfo"),
        )


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """``GET /api/v1/system/status``."""

    version: str
    zones: int
    clients: int
    radios: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build the model from a decoded JSON object."""
        return cls(
            version=_require(data, "version", str, "SystemStatus"),
            zones=_require(data, "zones", int, "SystemStatus"),
            clients=_require(data, "clients", int, "SystemStatus"),
            radios=_require(data, "radios", int, "SystemStatus"),
        )


@dataclass(frozen=True, slots=True)
class Zone:
    """``ZoneInfo``: one zone as ``GET /api/v1/zones`` returns it."""

    index: int
    name: str
    icon: str
    volume: int
    muted: bool
    playback: str
    source: str
    shuffle: bool
    repeat: str
    presence: bool
    presence_enabled: bool
    presence_timer_active: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build the model from a decoded JSON object."""
        what = "ZoneInfo"
        return cls(
            index=_require(data, "index", int, what),
            name=_require(data, "name", str, what),
            icon=_require(data, "icon", str, what),
            volume=_require(data, "volume", int, what),
            muted=_require(data, "muted", bool, what),
            playback=_require(data, "playback", str, what),
            source=_require(data, "source", str, what),
            shuffle=_require(data, "shuffle", bool, what),
            repeat=_require(data, "repeat", str, what),
            presence=_require(data, "presence", bool, what),
            presence_enabled=_require(data, "presence_enabled", bool, what),
            presence_timer_active=_require(data, "presence_timer_active", bool, what),
        )
