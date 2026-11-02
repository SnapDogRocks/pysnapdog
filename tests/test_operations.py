# SPDX-License-Identifier: Apache-2.0
"""Every library call against the spec-built fake server: verb, path and body on the wire."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
import pytest

from pysnapdog import (
    EqBand,
    EqConfig,
    FilterType,
    RepeatMode,
    SnapDogClient,
    UpdateConfig,
)

from .conftest import API_KEY, Fake

BAND = EqBand(freq=100.0, gain=-3.0, q=0.7, type=FilterType.LOW_SHELF)
EQ = EqConfig(enabled=True, bands=(BAND,), preset="custom")
BAND_JSON = {"freq": 100.0, "gain": -3.0, "q": 0.7, "type": "low_shelf"}
EQ_JSON = {"enabled": True, "bands": [BAND_JSON], "preset": "custom"}

Call = Callable[[SnapDogClient], Awaitable[Any]]


@dataclass(frozen=True)
class Case:
    """One library call and the request it must produce."""

    operation: str  # "METHOD /api/v1/path/template", as in the spec
    call: Call
    path: str  # the concrete path the call must request
    body: Any = None


def case(operation: str, call: Call, path: str, body: Any = None) -> Case:
    """Shorthand for a ``Case``."""
    return Case(operation, call, f"/api/v1{path}", body)


def op(verb: str, template: str) -> str:
    """The key of an operation."""
    return f"{verb} /api/v1{template}"


Z = "/zones/{zone_index}"
C = "/clients/{client_index}"

CASES: list[Case] = [
    # System
    case(op("GET", "/system/version"), lambda c: c.version(), "/system/version"),
    case(op("GET", "/system/status"), lambda c: c.status(), "/system/status"),
    case(op("GET", "/system/listeners"), lambda c: c.listeners(), "/system/listeners"),
    case(op("GET", "/system/updates"), lambda c: c.update_status(), "/system/updates"),
    case(
        op("POST", "/system/updates/check"),
        lambda c: c.check_for_updates(),
        "/system/updates/check",
    ),
    case(op("POST", "/system/updates/apply"), lambda c: c.apply_update(), "/system/updates/apply"),
    case(
        op("POST", "/system/updates/config"),
        lambda c: c.configure_updates(UpdateConfig("auto", "03:00", "Europe/Berlin")),
        "/system/updates/config",
        {"mode": "auto", "maintenanceTime": "03:00", "timezone": "Europe/Berlin"},
    ),
    # KNX
    case(
        op("GET", "/knx/programming-mode"),
        lambda c: c.knx_programming_mode(),
        "/knx/programming-mode",
    ),
    case(
        op("PUT", "/knx/programming-mode"),
        lambda c: c.set_knx_programming_mode(True),
        "/knx/programming-mode",
        True,
    ),
    case(op("GET", "/knx/product-info"), lambda c: c.knx_product_info(), "/knx/product-info"),
    case(op("GET", "/knx/knxprod"), lambda c: c.knx_product_file(), "/knx/knxprod"),
    # EQ presets and speaker profiles
    case(op("GET", "/eq/presets"), lambda c: c.eq_presets(), "/eq/presets"),
    case(op("GET", "/speakers"), lambda c: c.speakers(), "/speakers"),
    case(
        op("GET", "/speakers/{name}/profile"),
        lambda c: c.speaker_profile("Neumann KH 80"),
        "/speakers/Neumann%20KH%2080/profile",
    ),
    # Zones: reads
    case(op("GET", "/zones"), lambda c: c.zones(), "/zones"),
    case(op("GET", Z), lambda c: c.zone(2), "/zones/2"),
    case(op("GET", "/zones/count"), lambda c: c.zone_count(), "/zones/count"),
    case(op("GET", f"{Z}/clients"), lambda c: c.zone_clients(2), "/zones/2/clients"),
    case(op("GET", f"{Z}/track/metadata"), lambda c: c.zone_track(2), "/zones/2/track/metadata"),
    case(op("GET", f"{Z}/playlist/info"), lambda c: c.zone_playlist(2), "/zones/2/playlist/info"),
    case(op("GET", f"{Z}/cover"), lambda c: c.zone_cover(2), "/zones/2/cover"),
    case(
        op("GET", f"{Z}/presence/timeout"),
        lambda c: c.zone_presence_timeout(2),
        "/zones/2/presence/timeout",
    ),
    # Zones: transport
    case(op("POST", f"{Z}/play"), lambda c: c.play(2), "/zones/2/play"),
    case(op("POST", f"{Z}/pause"), lambda c: c.pause(2), "/zones/2/pause"),
    case(op("POST", f"{Z}/stop"), lambda c: c.stop(2), "/zones/2/stop"),
    case(op("POST", f"{Z}/next"), lambda c: c.next_track(2), "/zones/2/next"),
    case(op("POST", f"{Z}/previous"), lambda c: c.previous_track(2), "/zones/2/previous"),
    case(
        op("PUT", f"{Z}/track/position"),
        lambda c: c.seek(2, position_ms=61000),
        "/zones/2/track/position",
        {"position_ms": 61000},
    ),
    case(
        op("PUT", f"{Z}/track/progress"),
        lambda c: c.seek_progress(2, 0.25),
        "/zones/2/track/progress",
        0.25,
    ),
    # Zones: volume, mute, shuffle, repeat
    case(op("PUT", f"{Z}/volume"), lambda c: c.set_zone_volume(2, 35), "/zones/2/volume", 35),
    case(op("PUT", f"{Z}/mute"), lambda c: c.set_zone_mute(2, True), "/zones/2/mute", True),
    case(op("POST", f"{Z}/mute/toggle"), lambda c: c.toggle_zone_mute(2), "/zones/2/mute/toggle"),
    case(
        op("PUT", f"{Z}/shuffle"), lambda c: c.set_zone_shuffle(2, False), "/zones/2/shuffle", False
    ),
    case(
        op("POST", f"{Z}/shuffle/toggle"),
        lambda c: c.toggle_zone_shuffle(2),
        "/zones/2/shuffle/toggle",
    ),
    case(
        op("PUT", f"{Z}/repeat"),
        lambda c: c.set_zone_repeat(2, RepeatMode.PLAYLIST),
        "/zones/2/repeat",
        "playlist",
    ),
    case(
        op("POST", f"{Z}/repeat/toggle"),
        lambda c: c.toggle_zone_repeat(2),
        "/zones/2/repeat/toggle",
    ),
    # Zones: what to play
    case(op("PUT", f"{Z}/playlist"), lambda c: c.set_zone_playlist(2, 3), "/zones/2/playlist", 3),
    case(
        op("GET", f"{Z}/playlist/by-id"),
        lambda c: c.zone_playlist_id(2),
        "/zones/2/playlist/by-id",
    ),
    case(
        op("PUT", f"{Z}/playlist/by-id"),
        lambda c: c.set_zone_playlist_id(2, "subsonic:42"),
        "/zones/2/playlist/by-id",
        "subsonic:42",
    ),
    case(op("POST", f"{Z}/next/playlist"), lambda c: c.next_playlist(2), "/zones/2/next/playlist"),
    case(
        op("POST", f"{Z}/previous/playlist"),
        lambda c: c.previous_playlist(2),
        "/zones/2/previous/playlist",
    ),
    case(op("POST", f"{Z}/play/track"), lambda c: c.play_track(2, 7), "/zones/2/play/track", 7),
    case(
        op("POST", f"{Z}/play/playlist"),
        lambda c: c.play_playlist(2, 3, 4),
        "/zones/2/play/playlist",
        {"index": 3, "track": 4},
    ),
    case(
        op("POST", f"{Z}/play/playlist/by-id"),
        lambda c: c.play_playlist_id(2, "subsonic:42", 4),
        "/zones/2/play/playlist/by-id",
        {"playlist_id": "subsonic:42", "track": 4},
    ),
    case(
        op("POST", f"{Z}/play/playlist/{{playlist_index}}/track"),
        lambda c: c.play_playlist_track(2, 3, 4),
        "/zones/2/play/playlist/3/track",
        4,
    ),
    case(
        op("POST", f"{Z}/play/subsonic/{{track_id}}"),
        lambda c: c.play_subsonic_track(2, "tr/1 x"),
        "/zones/2/play/subsonic/tr%2F1%20x",
    ),
    case(
        op("POST", f"{Z}/play/url"),
        lambda c: c.play_url(2, "http://example.org/stream.mp3"),
        "/zones/2/play/url",
        "http://example.org/stream.mp3",
    ),
    # Zones: presence
    case(
        op("PUT", f"{Z}/presence"),
        lambda c: c.set_zone_presence(2, True),
        "/zones/2/presence",
        True,
    ),
    case(
        op("PUT", f"{Z}/presence/enable"),
        lambda c: c.set_zone_presence_enabled(2, False),
        "/zones/2/presence/enable",
        False,
    ),
    case(
        op("PUT", f"{Z}/presence/timeout"),
        lambda c: c.set_zone_presence_timeout(2, 90),
        "/zones/2/presence/timeout",
        90,
    ),
    # Zones: equalizer
    case(op("GET", f"{Z}/eq"), lambda c: c.zone_eq(2), "/zones/2/eq"),
    case(op("PUT", f"{Z}/eq"), lambda c: c.set_zone_eq(2, EQ), "/zones/2/eq", EQ_JSON),
    case(
        op("PUT", f"{Z}/eq/{{band_index}}"),
        lambda c: c.set_zone_eq_band(2, 1, BAND),
        "/zones/2/eq/1",
        BAND_JSON,
    ),
    case(
        op("POST", f"{Z}/eq/preset"),
        lambda c: c.apply_zone_eq_preset(2, "rock"),
        "/zones/2/eq/preset",
        "rock",
    ),
    # Clients
    case(op("GET", "/clients"), lambda c: c.clients(), "/clients"),
    case(op("GET", C), lambda c: c.client(3), "/clients/3"),
    case(op("GET", "/clients/count"), lambda c: c.client_count(), "/clients/count"),
    case(op("GET", f"{C}/latency"), lambda c: c.client_latency(3), "/clients/3/latency"),
    case(
        op("PUT", f"{C}/volume"), lambda c: c.set_client_volume(3, "+5"), "/clients/3/volume", "+5"
    ),
    case(op("PUT", f"{C}/mute"), lambda c: c.set_client_mute(3, True), "/clients/3/mute", True),
    case(
        op("POST", f"{C}/mute/toggle"), lambda c: c.toggle_client_mute(3), "/clients/3/mute/toggle"
    ),
    case(
        op("PUT", f"{C}/latency"), lambda c: c.set_client_latency(3, -40), "/clients/3/latency", -40
    ),
    case(op("PUT", f"{C}/zone"), lambda c: c.set_client_zone(3, 2), "/clients/3/zone", 2),
    case(
        op("PUT", f"{C}/name"),
        lambda c: c.rename_client(3, "Kitchen"),
        "/clients/3/name",
        "Kitchen",
    ),
    case(op("GET", f"{C}/eq"), lambda c: c.client_eq(3), "/clients/3/eq"),
    case(op("PUT", f"{C}/eq"), lambda c: c.set_client_eq(3, EQ), "/clients/3/eq", EQ_JSON),
    case(
        op("PUT", f"{C}/eq/{{band_index}}"),
        lambda c: c.set_client_eq_band(3, 0, BAND),
        "/clients/3/eq/0",
        BAND_JSON,
    ),
    case(
        op("POST", f"{C}/eq/preset"),
        lambda c: c.apply_client_eq_preset(3, "flat"),
        "/clients/3/eq/preset",
        "flat",
    ),
    case(op("GET", f"{C}/speaker"), lambda c: c.client_speaker(3), "/clients/3/speaker"),
    case(
        op("PUT", f"{C}/speaker"),
        lambda c: c.apply_client_speaker(3, speaker="Neumann KH 80"),
        "/clients/3/speaker",
        {"speaker": "Neumann KH 80"},
    ),
    # Media
    case(op("GET", "/media/playlists"), lambda c: c.playlists(), "/media/playlists"),
    case(
        op("GET", "/media/playlists/{playlist_index}"),
        lambda c: c.playlist(1),
        "/media/playlists/1",
    ),
    case(
        op("GET", "/media/playlists/by-id/{playlist_id}"),
        lambda c: c.playlist_by_id("subsonic:a/b c"),
        "/media/playlists/by-id/subsonic:a%2Fb%20c",
    ),
    case(
        op("GET", "/media/playlists/by-id/{playlist_id}/tracks"),
        lambda c: c.playlist_tracks_by_id("snapdog:radio"),
        "/media/playlists/by-id/snapdog:radio/tracks",
    ),
    case(
        op("GET", "/media/playlists/{playlist_index}/tracks"),
        lambda c: c.playlist_tracks(1),
        "/media/playlists/1/tracks",
    ),
    case(
        op("GET", "/media/playlists/{playlist_index}/tracks/{track_index}"),
        lambda c: c.playlist_track(1, 2),
        "/media/playlists/1/tracks/2",
    ),
    case(
        op("GET", "/media/playlists/{playlist_index}/cover"),
        lambda c: c.playlist_cover(1),
        "/media/playlists/1/cover",
    ),
    case(
        op("GET", "/media/playlists/{playlist_index}/tracks/{track_index}/cover"),
        lambda c: c.track_cover(1, 2),
        "/media/playlists/1/tracks/2/cover",
    ),
]


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.operation)
async def test_the_call_produces_the_request_the_spec_describes(
    c: Case, session: aiohttp.ClientSession, fake: Fake
) -> None:
    client = SnapDogClient(session, fake.host, port=fake.port, api_key=API_KEY)
    await c.call(client)

    assert len(fake.calls) == 1, fake.calls
    seen = fake.last
    assert f"{seen.method} {seen.path}" == f"{c.operation.split()[0]} {c.path}"
    assert seen.body == c.body
    assert not fake.violations, fake.violations
    assert seen.headers["Authorization"] == f"Bearer {API_KEY}"
