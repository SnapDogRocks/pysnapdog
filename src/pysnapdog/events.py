# SPDX-License-Identifier: Apache-2.0
"""Events the server pushes on ``/ws``.

Every event carries absolute values, never a delta, and all of them travel on one
ordered channel. The field names follow ``asyncapi.json`` of the server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from .exceptions import SnapDogResponseError
from .models import JSON, EqConfig, RepeatMode, _enum, _optional, _playlist_index, _require


@dataclass(frozen=True, slots=True)
class ZoneChanged:
    """The full state of a zone, sent about once a second while it plays."""

    zone: int
    playback: str
    source: str
    shuffle: bool
    repeat: RepeatMode
    title: str
    artist: str
    album: str
    duration_ms: int
    position_ms: int
    seekable: bool
    can_next: bool
    can_prev: bool
    can_playlist_next: bool
    can_playlist_prev: bool
    volume: int
    muted: bool
    album_artist: str | None
    genre: str | None
    year: int | None
    track_number: int | None
    disc_number: int | None
    cover_url: str | None
    bitrate_kbps: int | None
    content_type: str | None
    track_index: int | None
    track_count: int | None
    playlist_index: int | None
    playlist_id: str | None
    playlist_name: str | None
    playlist_total: int | None
    sample_rate: int | None = None
    """The sample rate of the track in Hz, ``None`` when the track has none or the server does
    not send it."""

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object.

        ``playlist_id`` identifies the active playlist and is the value to remember and compare.
        ``playlist_index`` moves when the list changes. Against an older server that sends no
        ``playlist_index`` the event falls back to the deprecated ``playlist`` field for it, and
        ``playlist_id`` is ``None``.
        """
        what = "zone_changed"
        return cls(
            zone=_require(data, "zone", int, what),
            playback=_require(data, "playback", str, what),
            source=_require(data, "source", str, what),
            shuffle=_require(data, "shuffle", bool, what),
            repeat=_enum(RepeatMode, data, "repeat", what),
            title=_require(data, "title", str, what),
            artist=_require(data, "artist", str, what),
            album=_require(data, "album", str, what),
            duration_ms=_require(data, "duration_ms", int, what),
            position_ms=_require(data, "position_ms", int, what),
            seekable=_require(data, "seekable", bool, what),
            can_next=_require(data, "can_next", bool, what),
            can_prev=_require(data, "can_prev", bool, what),
            can_playlist_next=_require(data, "can_playlist_next", bool, what),
            can_playlist_prev=_require(data, "can_playlist_prev", bool, what),
            volume=_require(data, "volume", int, what),
            muted=_require(data, "muted", bool, what),
            album_artist=_optional(data, "album_artist", str, what),
            genre=_optional(data, "genre", str, what),
            year=_optional(data, "year", int, what),
            track_number=_optional(data, "track_number", int, what),
            disc_number=_optional(data, "disc_number", int, what),
            cover_url=_optional(data, "cover_url", str, what),
            bitrate_kbps=_optional(data, "bitrate_kbps", int, what),
            sample_rate=_optional(data, "sample_rate", int, what),
            content_type=_optional(data, "content_type", str, what),
            track_index=_optional(data, "track_index", int, what),
            track_count=_optional(data, "track_count", int, what),
            playlist_index=_playlist_index(data, "playlist_index", "playlist", what),
            playlist_id=_optional(data, "playlist_id", str, what),
            playlist_name=_optional(data, "playlist_name", str, what),
            playlist_total=_optional(data, "playlist_total", int, what),
        )

    @property
    def playlist(self) -> int | None:
        """``playlist_index`` under the name of the deprecated ``playlist`` field. Do not use."""
        return self.playlist_index


@dataclass(frozen=True, slots=True)
class ZoneVolumeChanged:
    """The volume or mute of a zone changed."""

    zone: int
    volume: int
    muted: bool

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        what = "zone_volume_changed"
        return cls(
            zone=_require(data, "zone", int, what),
            volume=_require(data, "volume", int, what),
            muted=_require(data, "muted", bool, what),
        )


@dataclass(frozen=True, slots=True)
class ZoneProgress:
    """The playback position of a zone. Reserved: the server does not send it yet."""

    zone: int
    position_ms: int
    duration_ms: int
    buffered_ms: int | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        what = "zone_progress"
        return cls(
            zone=_require(data, "zone", int, what),
            position_ms=_require(data, "position_ms", int, what),
            duration_ms=_require(data, "duration_ms", int, what),
            buffered_ms=_optional(data, "buffered_ms", int, what),
        )


@dataclass(frozen=True, slots=True)
class ClientStateChanged:
    """A client connected, disconnected, changed volume, mute or zone."""

    client: int
    volume: int
    muted: bool
    connected: bool
    zone: int
    is_snapdog: bool
    latency_ms: int | None = None
    """The latency correction in milliseconds, ``None`` from a server that does not send it."""
    name: str | None = None
    """The display name of the client, ``None`` from a server that does not send it."""

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        what = "client_state_changed"
        return cls(
            client=_require(data, "client", int, what),
            volume=_require(data, "volume", int, what),
            muted=_require(data, "muted", bool, what),
            connected=_require(data, "connected", bool, what),
            zone=_require(data, "zone", int, what),
            is_snapdog=_require(data, "is_snapdog", bool, what),
            latency_ms=_optional(data, "latency_ms", int, what),
            name=_optional(data, "name", str, what),
        )


@dataclass(frozen=True, slots=True)
class ZoneEqChanged:
    """The equalizer of a zone changed."""

    zone: int
    config: EqConfig

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        what = "zone_eq_changed"
        # The server flattens the EQ config into the event object.
        return cls(zone=_require(data, "zone", int, what), config=EqConfig.from_dict(data))


@dataclass(frozen=True, slots=True)
class ZonePresenceChanged:
    """The presence state of a zone changed."""

    zone: int
    presence: bool
    enabled: bool
    timer_active: bool

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        what = "zone_presence_changed"
        return cls(
            zone=_require(data, "zone", int, what),
            presence=_require(data, "presence", bool, what),
            enabled=_require(data, "enabled", bool, what),
            timer_active=_require(data, "timer_active", bool, what),
        )


@dataclass(frozen=True, slots=True)
class PlaybackError:
    """A zone could not play."""

    zone: int
    message: str
    details: str | None
    recoverable: bool

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        what = "playback_error"
        return cls(
            zone=_require(data, "zone", int, what),
            message=_require(data, "message", str, what),
            details=_optional(data, "details", str, what),
            recoverable=_require(data, "recoverable", bool, what),
        )


@dataclass(frozen=True, slots=True)
class PlaylistsChanged:
    """The list of playlists, an index or a name may have changed.

    Read ``SnapDogClient.playlists()`` again, and do so after a reconnect as well. ``total`` is the
    number of playlists now, the radio list included.
    """

    total: int

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the event from a decoded JSON object."""
        return cls(total=_require(data, "total", int, "playlists_changed"))


@dataclass(frozen=True, slots=True)
class UnknownEvent:
    """An event type this version of the library does not know. Newer servers may send them."""

    type: str
    data: JSON


type Event = (
    ZoneChanged
    | ZoneVolumeChanged
    | ZoneProgress
    | ClientStateChanged
    | ZoneEqChanged
    | ZonePresenceChanged
    | PlaybackError
    | PlaylistsChanged
    | UnknownEvent
)

_PARSERS: dict[str, Any] = {
    "zone_changed": ZoneChanged.from_dict,
    "zone_volume_changed": ZoneVolumeChanged.from_dict,
    "zone_progress": ZoneProgress.from_dict,
    "client_state_changed": ClientStateChanged.from_dict,
    "zone_eq_changed": ZoneEqChanged.from_dict,
    "zone_presence_changed": ZonePresenceChanged.from_dict,
    "playback_error": PlaybackError.from_dict,
    "playlists_changed": PlaylistsChanged.from_dict,
}

KNOWN_EVENT_TYPES = frozenset(_PARSERS)


def parse_event(data: Any) -> Event:  # noqa: ANN401
    """Turn one decoded JSON message into an event.

    A type the library does not know becomes ``UnknownEvent``, so a server that is newer
    than the library does not break the stream. A message that is not an object with a
    ``type``, or a known type with missing fields, raises ``SnapDogResponseError``.
    """
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        raise SnapDogResponseError("WebSocket message: expected an object with a 'type'")
    parser = _PARSERS.get(data["type"])
    if parser is None:
        return UnknownEvent(type=data["type"], data=data)
    event: Event = parser(data)
    return event
