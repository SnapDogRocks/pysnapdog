# SPDX-License-Identifier: Apache-2.0
"""Typed models of the SnapDog REST API (API version 1).

The field names follow ``openapi.json`` of the server. A response that lacks a
required field raises ``SnapDogResponseError`` instead of producing a half-filled
object. Fields the server marks as optional are ``None`` when absent or ``null``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self
from urllib.parse import unquote

from .exceptions import SnapDogResponseError

type JSON = dict[str, Any]


def _require(data: JSON, key: str, kind: type | tuple[type, ...], what: str) -> Any:  # noqa: ANN401
    """Return ``data[key]`` if it is there and of the expected type."""
    value = data.get(key)
    numeric = kind in (int, float, (int, float))
    if not isinstance(value, kind) or (numeric and isinstance(value, bool)):
        name = kind.__name__ if isinstance(kind, type) else "number"
        raise SnapDogResponseError(f"{what}: field {key!r} is missing or not {name}")
    return value


def _optional(data: JSON, key: str, kind: type, what: str) -> Any:  # noqa: ANN401
    """Return ``data[key]``, ``None`` if absent or ``null``, an error if of another type."""
    if data.get(key) is None:
        return None
    return _require(data, key, kind, what)


def _playlist_index(data: JSON, key: str, legacy: str, what: str) -> int | None:
    """The unified playlist index of a payload, from ``key`` or else from ``legacy``.

    Servers that know the playlist identity send ``key`` (``index``, ``playlist_index``) and
    ``playlist_id``. A payload without ``key`` comes from an older server, whose only name for
    the index is the deprecated ``legacy`` field (``id``, ``playlist``). This is the one place
    that reads it, so a client keeps working against older servers. A payload that has neither
    yields ``None``.
    """
    value: int | None = _optional(data, key, int, what)
    if value is None:
        value = _optional(data, legacy, int, what)
    return value


def _required_index(data: JSON, what: str) -> int:
    """``index`` of a playlist payload (see ``_playlist_index``), an error when there is none."""
    value = _playlist_index(data, "index", "id", what)
    if value is None:
        raise SnapDogResponseError(f"{what}: field 'index' is missing or not int")
    return value


def _number(data: JSON, key: str, what: str) -> float:
    """A JSON number, which the server may write with or without a fraction."""
    return float(_require(data, key, (int, float), what))


def _object(value: Any, what: str) -> JSON:  # noqa: ANN401
    if not isinstance(value, dict):
        raise SnapDogResponseError(f"{what}: expected a JSON object")
    return value


class RepeatMode(StrEnum):
    """How a zone repeats its playlist."""

    OFF = "off"
    TRACK = "track"
    PLAYLIST = "playlist"


class SearchKind(StrEnum):
    """What ``GET /media/search`` looks for and what a result is."""

    TRACK = "track"
    ALBUM = "album"
    PLAYLIST = "playlist"
    RADIO = "radio"


class FilterType(StrEnum):
    """Filter shape of one EQ band."""

    LOW_SHELF = "low_shelf"
    HIGH_SHELF = "high_shelf"
    PEAKING = "peaking"
    LOW_PASS = "low_pass"  # noqa: S105 - a filter shape, not a credential
    HIGH_PASS = "high_pass"  # noqa: S105 - a filter shape, not a credential


def _enum[E: StrEnum](kind: type[E], data: JSON, key: str, what: str) -> E:
    raw = _require(data, key, str, what)
    try:
        return kind(raw)
    except ValueError as err:
        raise SnapDogResponseError(f"{what}: field {key!r} has the unknown value {raw!r}") from err


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """``GET /api/v1/system/version``."""

    name: str
    version: str
    rust_version: str

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
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
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        return cls(
            version=_require(data, "version", str, "SystemStatus"),
            zones=_require(data, "zones", int, "SystemStatus"),
            clients=_require(data, "clients", int, "SystemStatus"),
            radios=_require(data, "radios", int, "SystemStatus"),
        )


@dataclass(frozen=True, slots=True)
class Listener:
    """One row of ``GET /api/v1/system/listeners``: a port the server opens."""

    service: str
    backend: str
    protocol: str
    address: str
    port: int
    bind_support: str
    note: str

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "Listener"
        return cls(
            service=_require(data, "service", str, what),
            backend=_require(data, "backend", str, what),
            protocol=_require(data, "protocol", str, what),
            address=_require(data, "address", str, what),
            port=_require(data, "port", int, what),
            bind_support=_require(data, "bind_support", str, what),
            note=_require(data, "note", str, what),
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
    repeat: RepeatMode
    presence: bool
    presence_enabled: bool
    presence_timer_active: bool

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
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
            repeat=_enum(RepeatMode, data, "repeat", what),
            presence=_require(data, "presence", bool, what),
            presence_enabled=_require(data, "presence_enabled", bool, what),
            presence_timer_active=_require(data, "presence_timer_active", bool, what),
        )


@dataclass(frozen=True, slots=True)
class Client:
    """``ClientInfo``: one speaker as ``GET /api/v1/clients`` returns it."""

    index: int
    name: str
    icon: str
    mac: str
    volume: int
    max_volume: int
    muted: bool
    connected: bool
    is_snapdog: bool
    zone_index: int

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "ClientInfo"
        return cls(
            index=_require(data, "index", int, what),
            name=_require(data, "name", str, what),
            icon=_require(data, "icon", str, what),
            mac=_require(data, "mac", str, what),
            volume=_require(data, "volume", int, what),
            max_volume=_require(data, "max_volume", int, what),
            muted=_require(data, "muted", bool, what),
            connected=_require(data, "connected", bool, what),
            is_snapdog=_require(data, "is_snapdog", bool, what),
            zone_index=_require(data, "zone_index", int, what),
        )


@dataclass(frozen=True, slots=True)
class TrackMetadata:
    """``ZoneTrackMetadata``: what a zone plays, from ``GET /zones/{n}/track/metadata``."""

    title: str
    artist: str
    album: str
    source: str
    duration_ms: int
    position_ms: int
    seekable: bool
    can_next: bool
    can_prev: bool
    can_playlist_next: bool
    can_playlist_prev: bool
    album_artist: str | None
    genre: str | None
    year: int | None
    track_number: int | None
    disc_number: int | None
    cover_url: str | None
    bitrate_kbps: int | None
    sample_rate: int | None
    content_type: str | None
    playlist_index: int | None
    playlist_id: str | None
    playlist_name: str | None
    playlist_total: int | None
    playlist_track_index: int | None
    playlist_track_count: int | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object.

        ``playlist_id`` is ``None`` when the server is too old to send it. Remember and compare
        playlists by ``playlist_id``, because ``playlist_index`` moves when the list changes.
        """
        what = "ZoneTrackMetadata"
        return cls(
            title=_require(data, "title", str, what),
            artist=_require(data, "artist", str, what),
            album=_require(data, "album", str, what),
            source=_require(data, "source", str, what),
            duration_ms=_require(data, "duration_ms", int, what),
            position_ms=_require(data, "position_ms", int, what),
            seekable=_require(data, "seekable", bool, what),
            can_next=_require(data, "can_next", bool, what),
            can_prev=_require(data, "can_prev", bool, what),
            can_playlist_next=_require(data, "can_playlist_next", bool, what),
            can_playlist_prev=_require(data, "can_playlist_prev", bool, what),
            album_artist=_optional(data, "album_artist", str, what),
            genre=_optional(data, "genre", str, what),
            year=_optional(data, "year", int, what),
            track_number=_optional(data, "track_number", int, what),
            disc_number=_optional(data, "disc_number", int, what),
            cover_url=_optional(data, "cover_url", str, what),
            bitrate_kbps=_optional(data, "bitrate_kbps", int, what),
            sample_rate=_optional(data, "sample_rate", int, what),
            content_type=_optional(data, "content_type", str, what),
            playlist_index=_optional(data, "playlist_index", int, what),
            playlist_id=_optional(data, "playlist_id", str, what),
            playlist_name=_optional(data, "playlist_name", str, what),
            playlist_total=_optional(data, "playlist_total", int, what),
            playlist_track_index=_optional(data, "playlist_track_index", int, what),
            playlist_track_count=_optional(data, "playlist_track_count", int, what),
        )


@dataclass(frozen=True, slots=True)
class ZonePlaylist:
    """``ZonePlaylistInfo``: the playlist a zone is on, from ``GET /zones/{n}/playlist/info``."""

    index: int | None
    playlist_id: str | None
    name: str | None
    total: int | None
    track_index: int | None
    track_count: int | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object.

        ``playlist_id`` is ``None`` when no playlist is active or the server is too old to send it.
        """
        what = "ZonePlaylistInfo"
        return cls(
            index=_optional(data, "index", int, what),
            playlist_id=_optional(data, "playlist_id", str, what),
            name=_optional(data, "name", str, what),
            total=_optional(data, "total", int, what),
            track_index=_optional(data, "track_index", int, what),
            track_count=_optional(data, "track_count", int, what),
        )


@dataclass(frozen=True, slots=True)
class Playlist:
    """``PlaylistInfo``: one entry of ``GET /api/v1/media/playlists``.

    ``playlist_id`` (``snapdog:radio`` or ``subsonic:<id>``) is the stable reference: remember and
    compare playlists by it. ``index`` is the unified index, which moves when playlists or radios
    are added or removed, so use it only to address an index endpoint right away.

    Against an older server that sends no ``index`` the model falls back to the deprecated ``id``
    field for ``index``, and ``playlist_id`` is ``None``.
    """

    index: int
    playlist_id: str | None
    name: str
    song_count: int
    duration: int
    cover_art: str | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "PlaylistInfo"
        return cls(
            index=_required_index(data, what),
            playlist_id=_optional(data, "playlist_id", str, what),
            name=_require(data, "name", str, what),
            song_count=_require(data, "song_count", int, what),
            duration=_require(data, "duration", int, what),
            cover_art=_optional(data, "cover_art", str, what),
        )

    @property
    def id(self) -> int:
        """The unified index, under the name of the deprecated ``id`` field. Use ``index``."""
        return self.index


@dataclass(frozen=True, slots=True)
class PlaylistDetails:
    """``PlaylistDetails``: ``GET /api/v1/media/playlists/{n}`` and ``.../by-id/{playlist_id}``.

    The same identity rules and the same fallback for older servers as ``Playlist``.
    """

    index: int
    playlist_id: str | None
    name: str
    tracks: int

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "PlaylistDetails"
        return cls(
            index=_required_index(data, what),
            playlist_id=_optional(data, "playlist_id", str, what),
            name=_require(data, "name", str, what),
            tracks=_require(data, "tracks", int, what),
        )

    @property
    def id(self) -> int:
        """The unified index, under the name of the deprecated ``id`` field. Use ``index``."""
        return self.index


@dataclass(frozen=True, slots=True)
class MediaTrack:
    """``MediaTrackInfo``: one track of a playlist."""

    id: str
    track: int
    title: str
    artist: str
    album: str
    duration: int
    cover_art: str | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "MediaTrackInfo"
        return cls(
            id=_require(data, "id", str, what),
            track=_require(data, "track", int, what),
            title=_require(data, "title", str, what),
            artist=_require(data, "artist", str, what),
            album=_require(data, "album", str, what),
            duration=_require(data, "duration", int, what),
            cover_art=_optional(data, "cover_art", str, what),
        )


@dataclass(frozen=True, slots=True)
class SearchItem:
    """``SearchItem``: one result of ``GET /api/v1/media/search``.

    The identifier has one field per kind and the others are ``None``:

    - track: ``track_id``, played with ``play_subsonic_track``
    - album: ``album_id``, played with ``play_subsonic_album``
    - playlist: ``playlist_id`` and ``index``, played with ``play_playlist_id``
    - radio: ``playlist_id`` (``snapdog:radio``) and ``track``, the position of the station

    ``cover_art`` is the path of a cover, and ``cover_id`` is the id for ``media_cover``.
    """

    kind: SearchKind
    title: str
    subtitle: str | None
    duration: int
    cover_art: str | None
    track_id: str | None
    album_id: str | None
    playlist_id: str | None
    index: int | None
    track: int | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "SearchItem"
        return cls(
            kind=_enum(SearchKind, data, "kind", what),
            title=_require(data, "title", str, what),
            subtitle=_optional(data, "subtitle", str, what),
            duration=_require(data, "duration", int, what),
            cover_art=_optional(data, "cover_art", str, what),
            track_id=_optional(data, "track_id", str, what),
            album_id=_optional(data, "album_id", str, what),
            playlist_id=_optional(data, "playlist_id", str, what),
            index=_optional(data, "index", int, what),
            track=_optional(data, "track", int, what),
        )

    @property
    def cover_id(self) -> str | None:
        """The id in ``cover_art`` (its last path segment), for ``SnapDogClient.media_cover``."""
        if self.cover_art is None:
            return None
        return unquote(self.cover_art.rsplit("/", 1)[-1])


@dataclass(frozen=True, slots=True)
class SearchResult:
    """``SearchResponse``: a page of search results.

    ``limit`` and ``offset`` apply to each kind, so a page holds up to ``limit`` results of every
    kind asked for. ``next_offset`` is the ``offset`` of the next page, ``None`` when no kind filled
    its page. A result of a kind this library does not know, from a newer server, is left out
    instead of failing the whole page.
    """

    items: tuple[SearchItem, ...]
    next_offset: int | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "SearchResponse"
        items = _require(data, "items", list, what)
        return cls(
            items=tuple(
                SearchItem.from_dict(row)
                for row in (_object(item, what) for item in items)
                if row.get("kind") in {kind.value for kind in SearchKind}
            ),
            next_offset=_optional(data, "next_offset", int, what),
        )


@dataclass(frozen=True, slots=True)
class EqBand:
    """One band of a parametric equalizer."""

    freq: float
    gain: float
    q: float
    type: FilterType

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "EqBand"
        return cls(
            freq=_number(data, "freq", what),
            gain=_number(data, "gain", what),
            q=_number(data, "q", what),
            type=_enum(FilterType, data, "type", what),
        )

    def to_dict(self) -> JSON:
        """The JSON object the server expects."""
        return {"freq": self.freq, "gain": self.gain, "q": self.q, "type": str(self.type)}


@dataclass(frozen=True, slots=True)
class EqConfig:
    """The equalizer of a zone or a client."""

    enabled: bool
    bands: tuple[EqBand, ...]
    preset: str | None = None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "EqConfig"
        bands = _require(data, "bands", list, what)
        return cls(
            enabled=_require(data, "enabled", bool, what),
            bands=tuple(EqBand.from_dict(_object(band, what)) for band in bands),
            preset=_optional(data, "preset", str, what),
        )

    def to_dict(self) -> JSON:
        """The JSON object the server expects."""
        body: JSON = {"enabled": self.enabled, "bands": [band.to_dict() for band in self.bands]}
        if self.preset is not None:
            body["preset"] = self.preset
        return body


@dataclass(frozen=True, slots=True)
class EqPreset:
    """A named EQ preset, from ``GET /api/v1/eq/presets``."""

    name: str
    bands: tuple[EqBand, ...]

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "EqPreset"
        bands = _require(data, "bands", list, what)
        return cls(
            name=_require(data, "name", str, what),
            bands=tuple(EqBand.from_dict(_object(band, what)) for band in bands),
        )


@dataclass(frozen=True, slots=True)
class UpdateProgress:
    """Progress of a running update."""

    phase: str
    detail: str | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "UpdateProgress"
        return cls(
            phase=_require(data, "phase", str, what),
            detail=_optional(data, "detail", str, what),
        )


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    """``UpdateStatus``: the self-update state of the server."""

    state: str
    update_mode: str
    update_available: bool
    maintenance_time: str
    timezone: str
    current_version: str | None
    available_version: str | None
    last_error: str | None
    progress: UpdateProgress | None

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "UpdateStatus"
        raw_progress = data.get("progress")
        progress = None if raw_progress is None else _object(raw_progress, what)
        return cls(
            state=_require(data, "state", str, what),
            update_mode=_require(data, "updateMode", str, what),
            update_available=_require(data, "updateAvailable", bool, what),
            maintenance_time=_require(data, "maintenanceTime", str, what),
            timezone=_require(data, "timezone", str, what),
            current_version=_optional(data, "currentVersion", str, what),
            available_version=_optional(data, "availableVersion", str, what),
            last_error=_optional(data, "lastError", str, what),
            progress=None if progress is None else UpdateProgress.from_dict(progress),
        )


@dataclass(frozen=True, slots=True)
class UpdateConfig:
    """The body of ``POST /api/v1/system/updates/config``."""

    mode: str
    maintenance_time: str
    timezone: str

    def to_dict(self) -> JSON:
        """The JSON object the server expects."""
        return {
            "mode": self.mode,
            "maintenanceTime": self.maintenance_time,
            "timezone": self.timezone,
        }


@dataclass(frozen=True, slots=True)
class ProductInfo:
    """``ProductInfo``: the KNX application the server presents to ETS."""

    application_number: str
    app_version: int
    hardware_version: int

    @classmethod
    def from_dict(cls, data: JSON) -> Self:
        """Build the model from a decoded JSON object."""
        what = "ProductInfo"
        return cls(
            application_number=_require(data, "application_number", str, what),
            app_version=_require(data, "app_version", int, what),
            hardware_version=_require(data, "hardware_version", int, what),
        )


@dataclass(frozen=True, slots=True)
class Image:
    """A cover as the server sends it."""

    content: bytes
    content_type: str
