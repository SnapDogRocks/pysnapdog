# SPDX-License-Identifier: Apache-2.0
"""Behaviour of the client that is not one operation: errors, results, arguments."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest
from aiohttp import web

from pysnapdog import (
    Client,
    EqBand,
    EqConfig,
    EqPreset,
    FilterType,
    Image,
    RepeatMode,
    SnapDogAuthError,
    SnapDogBusyError,
    SnapDogClient,
    SnapDogConnectionError,
    SnapDogError,
    SnapDogNotFoundError,
    SnapDogResponseError,
    SnapDogUnsupportedError,
    UpdateStatus,
    VersionInfo,
    Zone,
)

from .conftest import API_KEY, Fake

ZONE_VOLUME = ("PUT", "/api/v1/zones/{zone_index}/volume")


def client(session: aiohttp.ClientSession, fake: Fake, **kwargs: Any) -> SnapDogClient:
    options: dict[str, Any] = {"port": fake.port, "api_key": API_KEY, **kwargs}
    return SnapDogClient(session, fake.host, **options)


def json_override(fake: Fake, key: tuple[str, str], body: Any, status: int = 200) -> None:
    fake.overrides[key] = web.json_response(body, status=status)


# ── Results ─────────────────────────────────────────────────────────────────


async def test_results_are_typed_models(session: aiohttp.ClientSession, fake: Fake) -> None:
    api = client(session, fake)
    assert isinstance(await api.version(), VersionInfo)
    zones = await api.zones()
    assert zones
    assert all(isinstance(z, Zone) for z in zones)
    assert isinstance(zones[0].repeat, RepeatMode)
    assert all(isinstance(c, Client) for c in await api.clients())
    assert isinstance(await api.update_status(), UpdateStatus)
    assert all(isinstance(p, EqPreset) for p in await api.eq_presets())


async def test_a_cover_comes_with_its_content_type(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    image = await client(session, fake).zone_cover(1)
    assert image == Image(b"\x89PNG-bytes", "image/png")


async def test_a_client_call_returns_the_value_the_server_answered(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    api = client(session, fake)
    assert await api.set_client_volume(1, 50) == 1  # the generated answer, not the argument
    assert await api.set_client_mute(1, False) is True
    assert await api.rename_client(1, "Kitchen") == "x"


async def test_a_relative_volume_is_sent_as_a_string(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await client(session, fake).set_zone_volume(1, "-3")
    assert fake.last.body == "-3"


# ── Arguments ───────────────────────────────────────────────────────────────


async def test_seek_needs_exactly_one_target(session: aiohttp.ClientSession, fake: Fake) -> None:
    api = client(session, fake)
    with pytest.raises(ValueError, match="exactly one"):
        await api.seek(1)
    with pytest.raises(ValueError, match="exactly one"):
        await api.seek(1, position_ms=1, offset_ms=1)
    await api.seek(1, offset_ms=-500)
    assert fake.last.body == {"offset_ms": -500}
    assert len(fake.calls) == 1


async def test_a_speaker_needs_exactly_one_source(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    api = client(session, fake)
    custom = EqConfig(enabled=True, bands=(EqBand(1000, 0, 1, FilterType.PEAKING),))
    with pytest.raises(ValueError, match="exactly one"):
        await api.apply_client_speaker(1)
    with pytest.raises(ValueError, match="exactly one"):
        await api.apply_client_speaker(1, speaker="x", custom=custom)
    await api.apply_client_speaker(1, custom=custom)
    assert fake.last.body == {"custom": custom.to_dict()}
    assert not fake.violations


async def test_a_repeat_mode_the_server_does_not_know_is_refused_before_sending(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    with pytest.raises(ValueError, match="one"):
        await client(session, fake).set_zone_repeat(1, "one")
    assert not fake.calls


async def test_playing_a_playlist_without_a_track_omits_the_track(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await client(session, fake).play_playlist(1, 2)
    assert fake.last.body == {"index": 2}
    assert not fake.violations


async def test_playing_a_playlist_sends_index_and_never_id(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await client(session, fake).play_playlist(1, 2, 5)
    assert fake.last.body == {"index": 2, "track": 5}
    assert "id" not in fake.last.body
    assert not fake.violations


async def test_playing_a_playlist_by_id_without_a_track_omits_the_track(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await client(session, fake).play_playlist_id(1, "snapdog:radio")
    assert fake.last.body == {"playlist_id": "snapdog:radio"}
    assert not fake.violations


async def test_the_playlist_id_of_a_zone_is_none_when_no_playlist_is_active(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    key = ("GET", "/api/v1/zones/{zone_index}/playlist/by-id")
    fake.overrides[key] = web.json_response("")
    assert await client(session, fake).zone_playlist_id(1) is None
    fake.overrides[key] = web.json_response("subsonic:42")
    assert await client(session, fake).zone_playlist_id(1) == "subsonic:42"


@pytest.mark.parametrize(
    ("limit", "offset", "query"),
    [
        (None, None, ""),
        (5, None, "?limit=5"),
        (None, 10, "?offset=10"),
        (5, 10, "?limit=5&offset=10"),
    ],
)
async def test_track_lists_may_be_cut(
    session: aiohttp.ClientSession, fake: Fake, limit: int | None, offset: int | None, query: str
) -> None:
    c = client(session, fake)
    await c.playlist_tracks(1, limit=limit, offset=offset)
    assert fake.last.path == f"/api/v1/media/playlists/1/tracks{query}"
    await c.playlist_tracks_by_id("subsonic:7", limit=limit, offset=offset)
    assert fake.last.path == f"/api/v1/media/playlists/by-id/subsonic:7/tracks{query}"


async def test_a_negative_limit_or_offset_is_refused_before_sending(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    with pytest.raises(ValueError, match="negative"):
        await client(session, fake).playlist_tracks(1, limit=-1)
    with pytest.raises(ValueError, match="negative"):
        await client(session, fake).playlist_tracks_by_id("snapdog:radio", offset=-1)
    assert not fake.calls


async def test_an_unknown_playlist_id_is_not_found(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    fake.overrides[("GET", "/api/v1/media/playlists/by-id/{playlist_id}")] = web.json_response(
        {"error": "not_found", "message": "no such playlist"}, status=404
    )
    with pytest.raises(SnapDogNotFoundError, match="no such playlist"):
        await client(session, fake).playlist_by_id("subsonic:nope")


# ── Errors ──────────────────────────────────────────────────────────────────


async def test_the_key_goes_in_the_header_and_not_in_the_url(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await client(session, fake).version()
    assert fake.last.headers["Authorization"] == f"Bearer {API_KEY}"
    assert API_KEY not in fake.last.path


async def test_a_wrong_key_is_an_auth_error(session: aiohttp.ClientSession, fake: Fake) -> None:
    with pytest.raises(SnapDogAuthError):
        await client(session, fake, api_key="wrong").version()


async def test_no_key_sends_no_header(session: aiohttp.ClientSession, fake: Fake) -> None:
    with pytest.raises(SnapDogAuthError):
        await client(session, fake, api_key=None).version()
    assert "Authorization" not in fake.last.headers


async def test_connection_refused_is_a_connection_error(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await fake.server.close()
    with pytest.raises(SnapDogConnectionError):
        await client(session, fake).version()


async def test_every_error_is_a_snapdog_error(session: aiohttp.ClientSession, fake: Fake) -> None:
    with pytest.raises(SnapDogError):
        await client(session, fake, api_key="wrong").zones()


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, SnapDogNotFoundError),
        (422, SnapDogUnsupportedError),
        (503, SnapDogBusyError),
        (400, SnapDogResponseError),
        (500, SnapDogResponseError),
    ],
)
async def test_error_statuses_have_their_own_error(
    status: int, error: type[SnapDogResponseError], session: aiohttp.ClientSession, fake: Fake
) -> None:
    json_override(fake, ("GET", "/api/v1/zones/{zone_index}"), {"message": "nope"}, status)
    with pytest.raises(error) as info:
        await client(session, fake).zone(1)
    assert type(info.value) is error
    assert info.value.status == status
    assert info.value.detail == "nope"
    assert "nope" in str(info.value)


async def test_a_plain_text_error_body_is_kept_as_the_detail(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    fake.overrides[("GET", "/api/v1/zones/{zone_index}")] = web.Response(status=500, text="boom")
    with pytest.raises(SnapDogResponseError) as info:
        await client(session, fake).zone(1)
    assert info.value.detail == "boom"


async def test_an_error_without_a_body_has_no_detail(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    fake.overrides[("GET", "/api/v1/zones/{zone_index}")] = web.Response(status=500)
    with pytest.raises(SnapDogResponseError) as info:
        await client(session, fake).zone(1)
    assert info.value.detail is None


async def test_a_client_without_eq_is_unsupported(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    json_override(
        fake,
        ("GET", "/api/v1/clients/{client_index}/eq"),
        {"error": "unprocessable", "message": "Client does not support EQ (not a SnapDog client)"},
        422,
    )
    with pytest.raises(SnapDogUnsupportedError, match="not a SnapDog client"):
        await client(session, fake).client_eq(1)


async def test_a_body_that_is_not_json_is_refused(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    fake.overrides[("GET", "/api/v1/zones/{zone_index}")] = web.Response(text="<html>")
    with pytest.raises(SnapDogResponseError, match="not JSON"):
        await client(session, fake).zone(1)


@pytest.mark.parametrize(
    ("call", "body", "message"),
    [
        (lambda c: c.zone(1), [], "expected a JSON object"),
        (lambda c: c.zones(), {"zones": []}, "expected a JSON array"),
        (lambda c: c.zones(), ["not an object"], "array of JSON objects"),
        (lambda c: c.zone_clients(1), ["1"], "array of integers"),
        (lambda c: c.zone_clients(1), [True], "array of integers"),
        (lambda c: c.speakers(), [1], "array of strings"),
        (lambda c: c.zone_count(), "3", "expected an integer"),
        (lambda c: c.zone_count(), True, "expected an integer"),
        (lambda c: c.knx_programming_mode(), 1, "expected a boolean"),
        (lambda c: c.rename_client(1, "x"), 5, "expected a string"),
        (lambda c: c.version(), {"name": "SnapDog"}, "'version'"),
    ],
)
async def test_an_answer_of_the_wrong_shape_is_refused(
    call: Any,
    body: Any,
    message: str,
    session: aiohttp.ClientSession,
    fake: Fake,
) -> None:
    for key in [
        ("GET", "/api/v1/zones/{zone_index}"),
        ("GET", "/api/v1/zones"),
        ("GET", "/api/v1/zones/{zone_index}/clients"),
        ("GET", "/api/v1/speakers"),
        ("GET", "/api/v1/zones/count"),
        ("GET", "/api/v1/knx/programming-mode"),
        ("PUT", "/api/v1/clients/{client_index}/name"),
        ("GET", "/api/v1/system/version"),
    ]:
        fake.overrides[key] = web.json_response(body)
    with pytest.raises(SnapDogResponseError, match=message):
        await call(client(session, fake))


# ── Addresses ───────────────────────────────────────────────────────────────


async def test_the_urls_carry_no_credentials(session: aiohttp.ClientSession, fake: Fake) -> None:
    plain = client(session, fake)
    assert plain.base_url == f"http://{fake.host}:{fake.port}/api/v1"
    assert plain.ws_url == f"ws://{fake.host}:{fake.port}/ws"
    secure = client(session, fake, tls=True, verify_tls=False)
    assert secure.base_url == f"https://{fake.host}:{fake.port}/api/v1"
    assert secure.ws_url == f"wss://{fake.host}:{fake.port}/ws"
    assert secure.verify_tls is False
    assert secure.session is session
    for url in (plain.base_url, plain.ws_url, secure.base_url, secure.ws_url):
        assert API_KEY not in url
    assert secure.headers == {"Authorization": f"Bearer {API_KEY}"}
    assert client(session, fake, api_key=None).headers == {}


async def test_the_headers_are_a_copy(session: aiohttp.ClientSession, fake: Fake) -> None:
    api = client(session, fake)
    api.headers["Authorization"] = "changed"
    assert api.headers["Authorization"] == f"Bearer {API_KEY}"
