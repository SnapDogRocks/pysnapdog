# SPDX-License-Identifier: Apache-2.0
"""A fake SnapDog server whose answers follow openapi.json of the server."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

ZONE: dict[str, Any] = {
    "index": 1,
    "name": "Ground Floor",
    "icon": "🏠",
    "volume": 40,
    "muted": False,
    "playback": "playing",
    "source": "radio",
    "shuffle": False,
    "repeat": "off",
    "presence": False,
    "presence_enabled": True,
    "presence_timer_active": False,
}

API_KEY = "s3cret"


class Fake:
    """The server under test, with the requests it has seen."""

    def __init__(self, server: TestServer, seen: list[web.Request]) -> None:
        self.server = server
        self.seen = seen
        # Read once: a closed TestServer forgets its port, and one test closes the server.
        assert server.port is not None
        self.host = str(server.host)
        self.port: int = server.port
        self.zones_body: Any = None  # set to make GET /zones answer something else


Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
async def fake() -> AsyncIterator[Fake]:
    seen: list[web.Request] = []

    async def record(request: web.Request) -> None:
        seen.append(request)

    @web.middleware
    async def auth(request: web.Request, handler: Handler) -> web.StreamResponse:
        await record(request)
        if request.headers.get("Authorization") != f"Bearer {API_KEY}":
            return web.Response(status=401, text="Invalid or missing API key")
        return await handler(request)

    async def version(_: web.Request) -> web.Response:
        return web.json_response({"name": "SnapDog", "version": "0.29.1", "rust_version": "1.90"})

    async def status(_: web.Request) -> web.Response:
        return web.json_response({"version": "0.29.1", "zones": 2, "clients": 3, "radios": 5})

    async def zones(_: web.Request) -> web.Response:
        if fake_ref.zones_body is not None:
            return web.json_response(fake_ref.zones_body)
        return web.json_response([ZONE, {**ZONE, "index": 2, "name": "Garden"}])

    async def zone(request: web.Request) -> web.Response:
        if request.match_info["n"] != "1":
            return web.Response(status=404, text="no such zone")
        return web.json_response(ZONE)

    async def broken(_: web.Request) -> web.Response:
        return web.Response(status=500, text="boom")

    async def not_json(_: web.Request) -> web.Response:
        return web.Response(text="<html>", content_type="text/html")

    async def incomplete(_: web.Request) -> web.Response:
        return web.json_response({"name": "SnapDog"})

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/v1/system/version", version)
    app.router.add_get("/api/v1/system/status", status)
    app.router.add_get("/api/v1/zones", zones)
    app.router.add_get("/api/v1/zones/{n}", zone)
    app.router.add_get("/api/v1/test/broken", broken)
    app.router.add_get("/api/v1/test/not-json", not_json)
    app.router.add_get("/api/v1/test/incomplete", incomplete)

    server = TestServer(app)
    await server.start_server()
    fake_ref = Fake(server, seen)
    try:
        yield fake_ref
    finally:
        await server.close()
