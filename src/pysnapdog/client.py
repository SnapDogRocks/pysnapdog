# SPDX-License-Identifier: Apache-2.0
"""Async REST client for a SnapDog server."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

from .exceptions import (
    SnapDogAuthError,
    SnapDogBusyError,
    SnapDogConnectionError,
    SnapDogNotFoundError,
    SnapDogReadOnlyError,
    SnapDogResponseError,
    SnapDogUnsupportedError,
    SnapDogUpstreamError,
)
from .models import (
    JSON,
    Client,
    EqBand,
    EqConfig,
    EqPreset,
    Image,
    Listener,
    MediaTrack,
    Playlist,
    PlaylistDetails,
    ProductInfo,
    RepeatMode,
    SearchKind,
    SearchResult,
    SystemStatus,
    TrackMetadata,
    UpdateConfig,
    UpdateStatus,
    VersionInfo,
    Zone,
    ZonePlaylist,
)

DEFAULT_PORT = 5555
DEFAULT_TIMEOUT = 10.0

_NO_BODY: Any = object()
_ERRORS: dict[int, type[SnapDogResponseError]] = {
    403: SnapDogReadOnlyError,
    404: SnapDogNotFoundError,
    422: SnapDogUnsupportedError,
    502: SnapDogUpstreamError,
    503: SnapDogBusyError,
}


class SnapDogClient:
    """Talk to one SnapDog server.

    The caller owns the ``aiohttp.ClientSession`` (Home Assistant hands its own in),
    so the client never opens or closes a session itself. The API key travels in the
    ``Authorization: Bearer`` header and never in a URL.

    Indexes of zones and clients are 1-based, as in the server's API. Commands that
    change a zone's playback return nothing: the new state arrives as an event on the
    WebSocket (see ``SnapDogListener``). Calls on clients return the new value.
    """

    def __init__(  # noqa: PLR0913 - keyword-only options of a public constructor
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        api_key: str | None = None,
        tls: bool = False,
        verify_tls: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Remember how to reach the server. Nothing is sent yet."""
        self._session = session
        self._authority = f"{host}:{port}"
        self._tls = tls
        self._base = f"{'https' if tls else 'http'}://{self._authority}/api/v1"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._ssl = verify_tls
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def base_url(self) -> str:
        """The API root, without credentials."""
        return self._base

    @property
    def ws_url(self) -> str:
        """The WebSocket address, without credentials."""
        return f"{'wss' if self._tls else 'ws'}://{self._authority}/ws"

    @property
    def session(self) -> aiohttp.ClientSession:
        """The session the caller handed in."""
        return self._session

    @property
    def headers(self) -> dict[str, str]:
        """The authentication headers, for the WebSocket upgrade."""
        return dict(self._headers)

    @property
    def verify_tls(self) -> bool:
        """Whether the server's certificate is verified."""
        return self._ssl

    # ── System ──────────────────────────────────────────────────────────────

    async def version(self) -> VersionInfo:
        """Read ``GET /system/version``."""
        return VersionInfo.from_dict(await self._object("GET", "/system/version"))

    async def status(self) -> SystemStatus:
        """Read ``GET /system/status``."""
        return SystemStatus.from_dict(await self._object("GET", "/system/status"))

    async def listeners(self) -> list[Listener]:
        """Read ``GET /system/listeners``: the ports the server opens."""
        return [Listener.from_dict(row) for row in await self._objects("GET", "/system/listeners")]

    async def update_status(self) -> UpdateStatus:
        """Read ``GET /system/updates``."""
        return UpdateStatus.from_dict(await self._object("GET", "/system/updates"))

    async def check_for_updates(self) -> UpdateStatus:
        """Ask the server to look for a new version (``POST /system/updates/check``)."""
        return UpdateStatus.from_dict(await self._object("POST", "/system/updates/check"))

    async def apply_update(self) -> UpdateStatus:
        """Start the update that is available (``POST /system/updates/apply``)."""
        return UpdateStatus.from_dict(await self._object("POST", "/system/updates/apply"))

    async def configure_updates(self, config: UpdateConfig) -> UpdateStatus:
        """Set the update mode and maintenance window (``POST /system/updates/config``)."""
        body = await self._object("POST", "/system/updates/config", json=config.to_dict())
        return UpdateStatus.from_dict(body)

    # ── KNX ─────────────────────────────────────────────────────────────────

    async def knx_programming_mode(self) -> bool:
        """Read ``GET /knx/programming-mode``."""
        return await self._bool("GET", "/knx/programming-mode")

    async def set_knx_programming_mode(self, enabled: bool) -> bool:  # noqa: FBT001
        """Switch the KNX programming mode (``PUT /knx/programming-mode``)."""
        return await self._bool("PUT", "/knx/programming-mode", json=enabled)

    async def knx_product_info(self) -> ProductInfo:
        """Read ``GET /knx/product-info``."""
        return ProductInfo.from_dict(await self._object("GET", "/knx/product-info"))

    async def knx_product_file(self) -> bytes:
        """Download the ``.knxprod`` file for ETS (``GET /knx/knxprod``)."""
        return (await self._download("/knx/knxprod")).content

    # ── Equalizer presets and speaker profiles ──────────────────────────────

    async def eq_presets(self) -> list[EqPreset]:
        """Read ``GET /eq/presets``: every preset name with its bands."""
        return [EqPreset.from_dict(item) for item in await self._objects("GET", "/eq/presets")]

    async def speakers(self) -> list[str]:
        """Read ``GET /speakers``: the speaker profiles the server can apply.

        Raises ``SnapDogBusyError`` when the server cannot reach its profile source.
        """
        return await self._strings("GET", "/speakers")

    async def speaker_profile(self, name: str) -> EqConfig:
        """Read ``GET /speakers/{name}/profile``: the correction for one speaker."""
        return EqConfig.from_dict(await self._object("GET", f"/speakers/{_segment(name)}/profile"))

    # ── Zones: reads ────────────────────────────────────────────────────────

    async def zones(self) -> list[Zone]:
        """Read ``GET /zones``."""
        return [Zone.from_dict(item) for item in await self._objects("GET", "/zones")]

    async def zone(self, index: int) -> Zone:
        """Read ``GET /zones/{index}``."""
        return Zone.from_dict(await self._object("GET", f"/zones/{index}"))

    async def zone_count(self) -> int:
        """Read ``GET /zones/count``."""
        return await self._int("GET", "/zones/count")

    async def zone_clients(self, index: int) -> list[int]:
        """Read ``GET /zones/{index}/clients``: the clients in the zone."""
        return await self._ints("GET", f"/zones/{index}/clients")

    async def zone_track(self, index: int) -> TrackMetadata:
        """Read ``GET /zones/{index}/track/metadata``: what the zone plays."""
        return TrackMetadata.from_dict(await self._object("GET", f"/zones/{index}/track/metadata"))

    async def zone_playlist(self, index: int) -> ZonePlaylist:
        """Read ``GET /zones/{index}/playlist/info``."""
        return ZonePlaylist.from_dict(await self._object("GET", f"/zones/{index}/playlist/info"))

    async def zone_playlist_id(self, index: int) -> str | None:
        """Read ``GET /zones/{index}/playlist/by-id``: the ``playlist_id`` the zone is on.

        ``None`` when no playlist is active.
        """
        return await self._string("GET", f"/zones/{index}/playlist/by-id") or None

    async def zone_cover(self, index: int) -> Image:
        """Download ``GET /zones/{index}/cover``. ``SnapDogNotFoundError`` when there is none."""
        return await self._download(f"/zones/{index}/cover")

    async def zone_presence_timeout(self, index: int) -> int:
        """Read ``GET /zones/{index}/presence/timeout``, in seconds."""
        return await self._int("GET", f"/zones/{index}/presence/timeout")

    # ── Zones: transport ────────────────────────────────────────────────────

    async def play(self, index: int) -> None:
        """Start or resume playback."""
        await self._command("POST", f"/zones/{index}/play")

    async def pause(self, index: int) -> None:
        """Pause playback."""
        await self._command("POST", f"/zones/{index}/pause")

    async def stop(self, index: int) -> None:
        """Stop playback."""
        await self._command("POST", f"/zones/{index}/stop")

    async def next_track(self, index: int) -> None:
        """Skip to the next track."""
        await self._command("POST", f"/zones/{index}/next")

    async def previous_track(self, index: int) -> None:
        """Go back to the previous track."""
        await self._command("POST", f"/zones/{index}/previous")

    async def seek(
        self, index: int, *, position_ms: int | None = None, offset_ms: int | None = None
    ) -> None:
        """Seek to ``position_ms`` or by ``offset_ms``. Exactly one of them is required."""
        if (position_ms is None) == (offset_ms is None):
            raise ValueError("give exactly one of position_ms and offset_ms")
        body = {"position_ms": position_ms} if offset_ms is None else {"offset_ms": offset_ms}
        await self._command("PUT", f"/zones/{index}/track/position", json=body)

    async def seek_progress(self, index: int, fraction: float) -> None:
        """Seek to a fraction of the track, from 0.0 to 1.0."""
        await self._command("PUT", f"/zones/{index}/track/progress", json=fraction)

    # ── Zones: volume, mute, shuffle, repeat ────────────────────────────────

    async def set_zone_volume(self, index: int, volume: int | str) -> int:
        """Set the volume: an absolute ``0..100`` or a relative ``"+5"`` / ``"-3"``.

        Returns the volume the server settled on. A relative value is added to the value the
        server last knew, which lags a moment behind a change made just before: send absolute
        values when you track the volume yourself.
        """
        return await self._int("PUT", f"/zones/{index}/volume", json=volume)

    async def set_zone_mute(self, index: int, muted: bool) -> None:  # noqa: FBT001
        """Mute or unmute the zone."""
        await self._command("PUT", f"/zones/{index}/mute", json=muted)

    async def toggle_zone_mute(self, index: int) -> None:
        """Toggle the mute of the zone."""
        await self._command("POST", f"/zones/{index}/mute/toggle")

    async def set_zone_shuffle(self, index: int, shuffle: bool) -> None:  # noqa: FBT001
        """Switch shuffle on or off."""
        await self._command("PUT", f"/zones/{index}/shuffle", json=shuffle)

    async def toggle_zone_shuffle(self, index: int) -> None:
        """Toggle shuffle."""
        await self._command("POST", f"/zones/{index}/shuffle/toggle")

    async def set_zone_repeat(self, index: int, mode: RepeatMode | str) -> None:
        """Set the repeat mode (``off``, ``track`` or ``playlist``)."""
        await self._command("PUT", f"/zones/{index}/repeat", json=str(RepeatMode(mode)))

    async def toggle_zone_repeat(self, index: int) -> None:
        """Step through the repeat modes."""
        await self._command("POST", f"/zones/{index}/repeat/toggle")

    # ── Zones: what to play ─────────────────────────────────────────────────

    async def set_zone_playlist(self, index: int, playlist: int) -> None:
        """Select a playlist by its unified index (``0`` is the radio list)."""
        await self._command("PUT", f"/zones/{index}/playlist", json=playlist)

    async def set_zone_playlist_id(self, index: int, playlist_id: str) -> None:
        """Select a playlist by its ``playlist_id`` (``PUT /zones/{index}/playlist/by-id``).

        An unknown ``playlist_id`` raises ``SnapDogNotFoundError``.
        """
        await self._command("PUT", f"/zones/{index}/playlist/by-id", json=playlist_id)

    async def next_playlist(self, index: int) -> None:
        """Select the next playlist."""
        await self._command("POST", f"/zones/{index}/next/playlist")

    async def previous_playlist(self, index: int) -> None:
        """Select the previous playlist."""
        await self._command("POST", f"/zones/{index}/previous/playlist")

    async def play_track(self, index: int, track: int) -> None:
        """Play a track of the active playlist."""
        await self._command("POST", f"/zones/{index}/play/track", json=track)

    async def play_playlist(self, index: int, playlist: int, track: int | None = None) -> None:
        """Switch to the playlist with the unified index ``playlist``, from ``track`` when given.

        The index moves when playlists change, so prefer ``play_playlist_id``. The request carries
        ``index``, never the deprecated ``id``.
        """
        body: JSON = {"index": playlist}
        if track is not None:
            body["track"] = track
        await self._command("POST", f"/zones/{index}/play/playlist", json=body)

    async def play_playlist_id(
        self, index: int, playlist_id: str, track: int | None = None
    ) -> None:
        """Switch to the playlist with this ``playlist_id`` and play it, from ``track`` when given.

        An unknown ``playlist_id`` raises ``SnapDogNotFoundError``.
        """
        body: JSON = {"playlist_id": playlist_id}
        if track is not None:
            body["track"] = track
        await self._command("POST", f"/zones/{index}/play/playlist/by-id", json=body)

    async def play_playlist_track(self, index: int, playlist: int, track: int) -> None:
        """Play one track of one playlist."""
        await self._command("POST", f"/zones/{index}/play/playlist/{playlist}/track", json=track)

    async def play_subsonic_album(self, index: int, album_id: str) -> None:
        """Queue the tracks of a Subsonic album and play it.

        ``POST /zones/{index}/play/subsonic/album/{album_id}``.

        An album is not part of the playlists list: the zone then names it in ``playlist_name``
        and has no ``playlist_index`` and no ``playlist_id``.
        """
        await self._command("POST", f"/zones/{index}/play/subsonic/album/{_segment(album_id)}")

    async def play_subsonic_track(self, index: int, track_id: str) -> None:
        """Play a Subsonic track by its id."""
        await self._command("POST", f"/zones/{index}/play/subsonic/{_segment(track_id)}")

    async def play_url(self, index: int, url: str) -> None:
        """Play an HTTP or HTTPS audio stream. ``SnapDogResponseError`` (400) for other URLs."""
        await self._command("POST", f"/zones/{index}/play/url", json=url)

    # ── Zones: presence ─────────────────────────────────────────────────────

    async def set_zone_presence(self, index: int, present: bool) -> None:  # noqa: FBT001
        """Report presence in the zone, or its end."""
        await self._command("PUT", f"/zones/{index}/presence", json=present)

    async def set_zone_presence_enabled(self, index: int, enabled: bool) -> None:  # noqa: FBT001
        """Switch the presence automation of the zone on or off."""
        await self._command("PUT", f"/zones/{index}/presence/enable", json=enabled)

    async def set_zone_presence_timeout(self, index: int, seconds: int) -> None:
        """Set the delay in seconds before the zone switches off after presence ends."""
        await self._command("PUT", f"/zones/{index}/presence/timeout", json=seconds)

    # ── Zones: equalizer ────────────────────────────────────────────────────

    async def zone_eq(self, index: int) -> EqConfig:
        """Read ``GET /zones/{index}/eq``."""
        return await self._eq("GET", f"/zones/{index}/eq")

    async def set_zone_eq(self, index: int, config: EqConfig) -> EqConfig:
        """Replace the zone's equalizer."""
        return await self._eq("PUT", f"/zones/{index}/eq", json=config.to_dict())

    async def set_zone_eq_band(self, index: int, band: int, value: EqBand) -> EqConfig:
        """Change one band (0-based) of the zone's equalizer."""
        return await self._eq("PUT", f"/zones/{index}/eq/{band}", json=value.to_dict())

    async def apply_zone_eq_preset(self, index: int, preset: str) -> EqConfig:
        """Apply a preset from ``eq_presets()``."""
        return await self._eq("POST", f"/zones/{index}/eq/preset", json=preset)

    # ── Clients ─────────────────────────────────────────────────────────────

    async def clients(self) -> list[Client]:
        """Read ``GET /clients``."""
        return [Client.from_dict(item) for item in await self._objects("GET", "/clients")]

    async def client(self, index: int) -> Client:
        """Read ``GET /clients/{index}``."""
        return Client.from_dict(await self._object("GET", f"/clients/{index}"))

    async def client_count(self) -> int:
        """Read ``GET /clients/count``."""
        return await self._int("GET", "/clients/count")

    async def client_latency(self, index: int) -> int:
        """Read ``GET /clients/{index}/latency``, in milliseconds."""
        return await self._int("GET", f"/clients/{index}/latency")

    async def set_client_volume(self, index: int, volume: int | str) -> int:
        """Set the volume: an absolute ``0..100`` or a relative ``"+5"`` / ``"-3"``.

        A relative value is added to the value the server last knew, which lags a moment behind
        a change made just before: send absolute values when you track the volume yourself.
        """
        return await self._int("PUT", f"/clients/{index}/volume", json=volume)

    async def set_client_mute(self, index: int, muted: bool) -> bool:  # noqa: FBT001
        """Mute or unmute the client. Returns the new state."""
        return await self._bool("PUT", f"/clients/{index}/mute", json=muted)

    async def toggle_client_mute(self, index: int) -> bool:
        """Toggle the mute of the client. Returns the new state."""
        return await self._bool("POST", f"/clients/{index}/mute/toggle")

    async def set_client_latency(self, index: int, milliseconds: int) -> int:
        """Set the latency correction in milliseconds."""
        return await self._int("PUT", f"/clients/{index}/latency", json=milliseconds)

    async def set_client_zone(self, index: int, zone: int) -> int:
        """Move the client to a zone. Returns the zone it is in now."""
        return await self._int("PUT", f"/clients/{index}/zone", json=zone)

    async def rename_client(self, index: int, name: str) -> str:
        """Change the client's name. Returns the name the server stored."""
        return await self._string("PUT", f"/clients/{index}/name", json=name)

    async def client_eq(self, index: int) -> EqConfig:
        """Read ``GET /clients/{index}/eq``. Raises ``SnapDogUnsupportedError`` if not SnapDog."""
        return await self._eq("GET", f"/clients/{index}/eq")

    async def set_client_eq(self, index: int, config: EqConfig) -> EqConfig:
        """Replace the client's equalizer."""
        return await self._eq("PUT", f"/clients/{index}/eq", json=config.to_dict())

    async def set_client_eq_band(self, index: int, band: int, value: EqBand) -> EqConfig:
        """Change one band (0-based) of the client's equalizer."""
        return await self._eq("PUT", f"/clients/{index}/eq/{band}", json=value.to_dict())

    async def apply_client_eq_preset(self, index: int, preset: str) -> EqConfig:
        """Apply a preset from ``eq_presets()``."""
        return await self._eq("POST", f"/clients/{index}/eq/preset", json=preset)

    async def client_speaker(self, index: int) -> EqConfig:
        """Read ``GET /clients/{index}/speaker``: the speaker correction in use."""
        return await self._eq("GET", f"/clients/{index}/speaker")

    async def apply_client_speaker(
        self, index: int, *, speaker: str | None = None, custom: EqConfig | None = None
    ) -> EqConfig:
        """Apply a speaker profile by name, or a custom EQ. Exactly one of them is required."""
        if (speaker is None) == (custom is None):
            raise ValueError("give exactly one of speaker and custom")
        body: JSON = {"speaker": speaker} if custom is None else {"custom": custom.to_dict()}
        return await self._eq("PUT", f"/clients/{index}/speaker", json=body)

    # ── Media ───────────────────────────────────────────────────────────────

    async def playlists(self) -> list[Playlist]:
        """Read ``GET /media/playlists``."""
        return [Playlist.from_dict(item) for item in await self._objects("GET", "/media/playlists")]

    async def playlist(self, index: int) -> PlaylistDetails:
        """Read ``GET /media/playlists/{index}``."""
        return PlaylistDetails.from_dict(await self._object("GET", f"/media/playlists/{index}"))

    async def playlist_by_id(self, playlist_id: str) -> PlaylistDetails:
        """Read ``GET /media/playlists/by-id/{playlist_id}``.

        An unknown ``playlist_id`` raises ``SnapDogNotFoundError``.
        """
        path = f"/media/playlists/by-id/{_segment(playlist_id)}"
        return PlaylistDetails.from_dict(await self._object("GET", path))

    async def playlist_tracks(
        self, index: int, *, limit: int | None = None, offset: int | None = None
    ) -> list[MediaTrack]:
        """Read ``GET /media/playlists/{index}/tracks``.

        With ``limit`` and/or ``offset`` the server cuts the same array. The total count it
        reports in ``X-Total-Count`` is not returned.
        """
        path = f"/media/playlists/{index}/tracks{_page(limit, offset)}"
        return [MediaTrack.from_dict(item) for item in await self._objects("GET", path)]

    async def playlist_tracks_by_id(
        self, playlist_id: str, *, limit: int | None = None, offset: int | None = None
    ) -> list[MediaTrack]:
        """Read ``.../by-id/{playlist_id}/tracks``, optionally cut as ``playlist_tracks``."""
        path = f"/media/playlists/by-id/{_segment(playlist_id)}/tracks{_page(limit, offset)}"
        return [MediaTrack.from_dict(item) for item in await self._objects("GET", path)]

    async def playlist_track(self, index: int, track: int) -> MediaTrack:
        """Read ``GET /media/playlists/{index}/tracks/{track}``."""
        body = await self._object("GET", f"/media/playlists/{index}/tracks/{track}")
        return MediaTrack.from_dict(body)

    async def playlist_cover(self, index: int) -> Image:
        """Download the cover of a playlist."""
        return await self._download(f"/media/playlists/{index}/cover")

    async def track_cover(self, index: int, track: int) -> Image:
        """Download the cover of a track."""
        return await self._download(f"/media/playlists/{index}/tracks/{track}/cover")

    async def media_cover(self, cover_id: str) -> Image:
        """Download ``GET /media/cover/{cover_id}``: the cover of a search result.

        ``SearchItem.cover_id`` is the id. ``SnapDogNotFoundError`` when the media server has none,
        ``SnapDogBusyError`` when no media server is configured.
        """
        return await self._download(f"/media/cover/{_segment(cover_id)}")

    # ── Media: search ───────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        kinds: Iterable[SearchKind] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> SearchResult:
        """Search tracks, albums, playlists and radio stations (``GET /media/search``).

        ``query`` needs at least two characters, the server answers 400 otherwise. Without ``kinds``
        every kind is searched. ``limit`` (default 20, at most 100) and ``offset`` apply to each
        kind, and ``SearchResult.next_offset`` is the ``offset`` of the next page. A media server
        that cannot be reached raises ``SnapDogUpstreamError``.
        """
        if (limit is not None and limit < 0) or (offset is not None and offset < 0):
            raise ValueError("limit and offset must not be negative")
        params: list[tuple[str, str | int]] = [("q", query)]
        if kinds is not None:
            params.append(("kind", ",".join(SearchKind(kind).value for kind in kinds)))
        params.extend(
            (key, value)
            for key, value in (("limit", limit), ("offset", offset))
            if value is not None
        )
        body = await self._object("GET", f"/media/search?{urlencode(params, quote_via=quote)}")
        return SearchResult.from_dict(body)

    # ── Media: manage playlists ─────────────────────────────────────────────
    #
    # The writes need ``[subsonic].playlist_write = true`` on the server and raise
    # ``SnapDogReadOnlyError`` without it, and always for ``snapdog:radio``. A refusal of the media
    # server (a user without the right to edit) raises ``SnapDogUpstreamError``. Address a playlist
    # by its ``playlist_id`` (``subsonic:<id>``), never by its index. A change is followed by the
    # ``PlaylistsChanged`` event.

    async def create_playlist(self, name: str, track_ids: Iterable[str] = ()) -> Playlist:
        """Create a playlist, with Subsonic track ids to start with if given.

        ``POST /media/playlists``.
        """
        body: JSON = {"name": name, "track_ids": list(track_ids)}
        return Playlist.from_dict(await self._object("POST", "/media/playlists", json=body))

    async def update_playlist(
        self,
        playlist_id: str,
        *,
        name: str | None = None,
        add_track_ids: Iterable[str] | None = None,
        remove_positions: Iterable[int] | None = None,
    ) -> PlaylistDetails:
        """Rename, append tracks and remove tracks (``PATCH /media/playlists/by-id/{playlist_id}``).

        ``add_track_ids`` are appended at the end. ``remove_positions`` are 0-based positions in the
        playlist as it is now. At least one of the three is required.
        """
        body: JSON = {}
        if name is not None:
            body["name"] = name
        if add_track_ids is not None:
            body["add_track_ids"] = list(add_track_ids)
        if remove_positions is not None:
            body["remove_positions"] = list(remove_positions)
        if not body:
            raise ValueError("give a name, tracks to add or positions to remove")
        path = f"/media/playlists/by-id/{_segment(playlist_id)}"
        return PlaylistDetails.from_dict(await self._object("PATCH", path, json=body))

    async def replace_playlist_tracks(
        self, playlist_id: str, track_ids: Iterable[str]
    ) -> PlaylistDetails:
        """Set the complete content and order of a playlist.

        ``PUT /media/playlists/by-id/{playlist_id}/tracks``.
        """
        path = f"/media/playlists/by-id/{_segment(playlist_id)}/tracks"
        body: JSON = {"track_ids": list(track_ids)}
        return PlaylistDetails.from_dict(await self._object("PUT", path, json=body))

    async def delete_playlist(self, playlist_id: str) -> None:
        """Delete a playlist (``DELETE /media/playlists/by-id/{playlist_id}``)."""
        await self._request("DELETE", f"/media/playlists/by-id/{_segment(playlist_id)}")

    # ── Transport ───────────────────────────────────────────────────────────

    async def _eq(self, method: str, path: str, *, json: Any = _NO_BODY) -> EqConfig:  # noqa: ANN401
        return EqConfig.from_dict(await self._object(method, path, json=json))

    async def _command(self, method: str, path: str, *, json: Any = _NO_BODY) -> None:  # noqa: ANN401
        """A zone command: it answers with an empty body and the result arrives as an event."""
        await self._request(method, path, json=json)

    async def _object(self, method: str, path: str, *, json: Any = _NO_BODY) -> JSON:  # noqa: ANN401
        body = await self._request(method, path, json=json)
        if not isinstance(body, dict):
            raise SnapDogResponseError(f"{method} {path}: expected a JSON object")
        return body

    async def _array(self, method: str, path: str) -> list[Any]:
        body = await self._request(method, path)
        if not isinstance(body, list):
            raise SnapDogResponseError(f"{method} {path}: expected a JSON array")
        return body

    async def _objects(self, method: str, path: str) -> list[JSON]:
        items = await self._array(method, path)
        if not all(isinstance(item, dict) for item in items):
            raise SnapDogResponseError(f"{method} {path}: expected an array of JSON objects")
        return items

    async def _ints(self, method: str, path: str) -> list[int]:
        items = await self._array(method, path)
        if not all(type(item) is int for item in items):
            raise SnapDogResponseError(f"{method} {path}: expected an array of integers")
        return items

    async def _strings(self, method: str, path: str) -> list[str]:
        items = await self._array(method, path)
        if not all(isinstance(item, str) for item in items):
            raise SnapDogResponseError(f"{method} {path}: expected an array of strings")
        return items

    async def _int(self, method: str, path: str, *, json: Any = _NO_BODY) -> int:  # noqa: ANN401
        body = await self._request(method, path, json=json)
        if type(body) is not int:
            raise SnapDogResponseError(f"{method} {path}: expected an integer")
        return body

    async def _bool(self, method: str, path: str, *, json: Any = _NO_BODY) -> bool:  # noqa: ANN401
        body = await self._request(method, path, json=json)
        if not isinstance(body, bool):
            raise SnapDogResponseError(f"{method} {path}: expected a boolean")
        return body

    async def _string(self, method: str, path: str, *, json: Any = _NO_BODY) -> str:  # noqa: ANN401
        body = await self._request(method, path, json=json)
        if not isinstance(body, str):
            raise SnapDogResponseError(f"{method} {path}: expected a string")
        return body

    async def _request(self, method: str, path: str, *, json: Any = _NO_BODY) -> Any:  # noqa: ANN401
        """Send one request. Returns the decoded JSON body, or ``None`` for an empty one."""
        kwargs: dict[str, Any] = {} if json is _NO_BODY else {"json": json}
        raw = await self._send(method, path, **kwargs)
        if not raw.content:
            return None
        try:
            return _decode(raw.content)
        except ValueError as err:
            raise SnapDogResponseError(f"{method} {path}: the body is not JSON") from err

    async def _download(self, path: str) -> Image:
        raw = await self._send("GET", path)
        return Image(raw.content, raw.content_type)

    async def _send(self, method: str, path: str, **kwargs: Any) -> _Raw:  # noqa: ANN401
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers,
                ssl=self._ssl,
                timeout=self._timeout,
                **kwargs,
            ) as response:
                content = await response.read()
                if response.status == 401:
                    raise SnapDogAuthError("the server rejected the API key")
                if response.status >= 400:
                    detail = _detail(content)
                    error = _ERRORS.get(response.status, SnapDogResponseError)
                    raise error(
                        f"{method} {path} failed with HTTP {response.status}"
                        + (f": {detail}" if detail else ""),
                        status=response.status,
                        detail=detail,
                    )
                return _Raw(content, response.content_type)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SnapDogConnectionError(
                f"cannot reach the server for {method} {path}: {err}"
            ) from err


class _Raw:
    """A successful response body with its content type."""

    __slots__ = ("content", "content_type")

    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.content_type = content_type


def _decode(content: bytes) -> Any:  # noqa: ANN401
    return json.loads(content)


def _detail(content: bytes) -> str | None:
    """The ``message`` of the server's error body, or its plain text."""
    try:
        body = json.loads(content)
    except ValueError:
        text = content.decode("utf-8", "replace").strip()
        return text or None
    message = body.get("message") if isinstance(body, dict) else None
    return message if isinstance(message, str) else None


def _segment(value: str) -> str:
    """A path segment: slashes and spaces in a speaker name or track id must not escape it."""
    return quote(value, safe="")


def _page(limit: int | None, offset: int | None) -> str:
    """The query string of a cut track list, empty without ``limit`` and ``offset``."""
    if (limit is not None and limit < 0) or (offset is not None and offset < 0):
        raise ValueError("limit and offset must not be negative")
    query = [
        f"{key}={value}"
        for key, value in (("limit", limit), ("offset", offset))
        if value is not None
    ]
    return f"?{'&'.join(query)}" if query else ""
