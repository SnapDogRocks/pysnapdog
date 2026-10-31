# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import aiohttp
import pytest

from pysnapdog import (
    SnapDogAuthError,
    SnapDogClient,
    SnapDogConnectionError,
    SnapDogError,
    SnapDogResponseError,
    VersionInfo,
)

from .conftest import API_KEY, ZONE, Fake


def client(session: aiohttp.ClientSession, fake: Fake, **kwargs: object) -> SnapDogClient:
    options: dict[str, object] = {"port": fake.port, "api_key": API_KEY, **kwargs}
    return SnapDogClient(session, fake.host, **options)  # type: ignore[arg-type]


async def test_version(session: aiohttp.ClientSession, fake: Fake) -> None:
    assert await client(session, fake).version() == VersionInfo("SnapDog", "0.29.1", "1.90")


async def test_status(session: aiohttp.ClientSession, fake: Fake) -> None:
    status = await client(session, fake).status()
    assert (status.zones, status.clients, status.radios) == (2, 3, 5)


async def test_zones(session: aiohttp.ClientSession, fake: Fake) -> None:
    zones = await client(session, fake).zones()
    assert [z.name for z in zones] == ["Ground Floor", "Garden"]
    assert zones[0].volume == ZONE["volume"]
    assert zones[0].presence_enabled is True


async def test_zone(session: aiohttp.ClientSession, fake: Fake) -> None:
    assert (await client(session, fake).zone(1)).name == "Ground Floor"


async def test_unknown_zone_is_a_response_error_with_status(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    with pytest.raises(SnapDogResponseError) as info:
        await client(session, fake).zone(9)
    assert info.value.status == 404


async def test_the_key_goes_in_the_header_and_not_in_the_url(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    await client(session, fake).version()
    request = fake.seen[-1]
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert API_KEY not in str(request.rel_url)


async def test_a_wrong_key_is_an_auth_error(session: aiohttp.ClientSession, fake: Fake) -> None:
    with pytest.raises(SnapDogAuthError):
        await client(session, fake, api_key="wrong").version()


async def test_no_key_sends_no_header(session: aiohttp.ClientSession, fake: Fake) -> None:
    with pytest.raises(SnapDogAuthError):
        await client(session, fake, api_key=None).version()
    assert "Authorization" not in fake.seen[-1].headers


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
    ("path", "message"),
    [
        ("/test/broken", "HTTP 500"),
        ("/test/not-json", "not JSON"),
    ],
)
async def test_bad_answers(
    session: aiohttp.ClientSession, fake: Fake, path: str, message: str
) -> None:
    api = client(session, fake)
    with pytest.raises(SnapDogResponseError, match=message):
        await api._get(path)


async def test_a_body_without_the_required_fields_is_rejected(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    api = client(session, fake)
    body = await api._get_object("/test/incomplete")
    with pytest.raises(SnapDogResponseError, match="'version'"):
        VersionInfo.from_dict(body)


async def test_the_base_url_carries_no_credentials(
    session: aiohttp.ClientSession, fake: Fake
) -> None:
    api = client(session, fake, tls=True)
    assert api.base_url == f"https://{fake.host}:{fake.port}/api/v1"
    assert API_KEY not in api.base_url


@pytest.mark.parametrize("body", [{"zones": []}, ["not an object"]])
async def test_zones_must_be_an_array_of_objects(
    session: aiohttp.ClientSession, fake: Fake, body: object
) -> None:
    fake.zones_body = body
    with pytest.raises(SnapDogResponseError, match="expected a JSON"):
        await client(session, fake).zones()
