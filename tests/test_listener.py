# SPDX-License-Identifier: Apache-2.0
"""The listener against a scripted WebSocket server."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import aiohttp
import pytest
from aiohttp import WSCloseCode, web
from aiohttp.test_utils import TestServer

from pysnapdog import (
    CLOSE_GOING_AWAY,
    CLOSE_TOO_SLOW,
    Event,
    SnapDogAuthError,
    SnapDogClient,
    SnapDogConnectionError,
    SnapDogConnectionLimitError,
    SnapDogError,
    SnapDogListener,
    UnknownEvent,
    ZoneVolumeChanged,
)

from .conftest import API_KEY

Script = Callable[[web.WebSocketResponse], Awaitable[None]]
VOLUME = {"type": "zone_volume_changed", "zone": 1, "volume": 30, "muted": False}


class WsServer:
    """A server that does what the next entry of ``script`` says, once per connection."""

    def __init__(self) -> None:
        self.script: deque[Script | int] = deque()
        self.connections = 0
        self.headers: list[dict[str, str]] = []

    async def handle(self, request: web.Request) -> web.StreamResponse:
        self.headers.append(dict(request.headers))
        if request.headers.get("Authorization") != f"Bearer {API_KEY}":
            return web.Response(status=401)
        step = self.script.popleft() if self.script else hold
        if isinstance(step, int):
            return web.Response(status=step)
        self.connections += 1
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await step(ws)
        return ws


async def hold(ws: web.WebSocketResponse) -> None:
    """Keep the connection open until the client goes."""
    async for _ in ws:
        pass


def sends(*messages: Any, then: Script = hold) -> Script:
    async def script(ws: web.WebSocketResponse) -> None:
        for message in messages:
            if isinstance(message, str):
                await ws.send_str(message)
            else:
                await ws.send_json(message)
        await then(ws)

    return script


def closes(code: int) -> Script:
    async def script(ws: web.WebSocketResponse) -> None:
        await ws.close(code=code)

    return script


@pytest.fixture
async def ws_server() -> AsyncIterator[tuple[WsServer, TestServer]]:
    state = WsServer()
    app = web.Application()
    app.router.add_get("/ws", state.handle)
    server = TestServer(app)
    await server.start_server()
    try:
        yield state, server
    finally:
        await server.close()


class Probe:
    """Collects what the listener calls."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.events: list[Event] = []
        self.errors: list[SnapDogError] = []
        self.connected_count = 0
        self.gate: asyncio.Event | None = None
        self.fail_connect: deque[SnapDogError] = deque()
        self.changed = asyncio.Event()

    async def on_event(self, event: Event) -> None:
        self.log.append("event")
        self.events.append(event)
        self.changed.set()

    async def on_connected(self) -> None:
        self.log.append("connected")
        self.connected_count += 1
        self.changed.set()
        if self.fail_connect:
            raise self.fail_connect.popleft()
        if self.gate is not None:
            await self.gate.wait()

    async def on_disconnected(self, error: SnapDogError) -> None:
        self.log.append("disconnected")
        self.errors.append(error)
        self.changed.set()

    async def until(self, condition: Callable[[], bool], timeout: float = 5.0) -> None:
        async def wait() -> None:
            while not condition():
                self.changed.clear()
                await self.changed.wait()

        await asyncio.wait_for(wait(), timeout)


def make(
    session: aiohttp.ClientSession,
    server: TestServer,
    probe: Probe,
    *,
    api_key: str | None = API_KEY,
) -> SnapDogListener:
    client = SnapDogClient(session, str(server.host), port=server.port or 0, api_key=api_key)
    return SnapDogListener(
        client,
        on_event=probe.on_event,
        on_connected=probe.on_connected,
        on_disconnected=probe.on_disconnected,
        backoff_min=0.01,
        backoff_max=0.04,
        heartbeat=5,
    )


async def test_events_that_arrive_while_the_state_is_read_are_delivered_after_it(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(sends(VOLUME, {**VOLUME, "volume": 31}))
    probe = Probe()
    probe.gate = asyncio.Event()
    listener = make(session, server, probe)

    listener.start()
    await probe.until(lambda: probe.connected_count == 1)
    await asyncio.sleep(0.1)
    assert probe.events == []  # buffered while the caller reads the state
    assert not listener.connected

    probe.gate.set()
    await probe.until(lambda: len(probe.events) == 2)
    assert probe.log[:3] == ["connected", "event", "event"]
    assert [e.volume for e in probe.events if isinstance(e, ZoneVolumeChanged)] == [30, 31]
    assert listener.connected
    await listener.stop()
    assert not listener.connected


async def test_the_key_goes_in_the_upgrade_request_header(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 1)
    await listener.stop()
    assert state.headers[0]["Authorization"] == f"Bearer {API_KEY}"


async def test_unknown_and_unreadable_messages_do_not_break_the_stream(
    session: aiohttp.ClientSession,
    ws_server: tuple[WsServer, TestServer],
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, server = ws_server
    state.script.append(
        sends("not json", {"no": "type"}, {"type": "future_event", "x": 1}, "[]", VOLUME)
    )
    probe = Probe()
    listener = make(session, server, probe)
    with caplog.at_level(logging.WARNING, logger="pysnapdog.listener"):
        listener.start()
        await probe.until(lambda: len(probe.events) == 2)
    await listener.stop()
    assert isinstance(probe.events[0], UnknownEvent)
    assert isinstance(probe.events[1], ZoneVolumeChanged)
    assert "unreadable" in caplog.text


async def test_a_binary_frame_is_ignored(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server

    async def script(ws: web.WebSocketResponse) -> None:
        await ws.send_bytes(b"\x00\x01")
        await ws.send_json(VOLUME)
        await hold(ws)

    state.script.append(script)
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: len(probe.events) == 1)
    await listener.stop()


async def test_too_slow_means_reconnect_at_once_and_read_the_state_again(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(closes(CLOSE_TOO_SLOW))
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 2)
    await listener.stop()
    assert probe.log[:3] == ["connected", "disconnected", "connected"]
    assert "too slow" in str(probe.errors[0])


async def test_a_server_shutdown_is_reported_and_retried_after_a_wait(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(closes(CLOSE_GOING_AWAY))
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 2)
    await listener.stop()
    assert "shutting down" in str(probe.errors[0])


async def test_any_other_close_is_reported_with_its_code(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(closes(WSCloseCode.INTERNAL_ERROR))
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 2)
    await listener.stop()
    assert "1011" in str(probe.errors[0])


async def test_a_wrong_key_ends_the_listener(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    _, server = ws_server
    probe = Probe()
    listener = make(session, server, probe, api_key="wrong")
    listener.start()
    await probe.until(lambda: bool(probe.errors))
    await asyncio.sleep(0.1)
    assert isinstance(listener.stopped_reason, SnapDogAuthError)
    assert isinstance(probe.errors[0], SnapDogAuthError)
    assert probe.connected_count == 0
    assert len(probe.errors) == 1  # no retry
    await listener.stop()


async def test_the_connection_limit_is_reported_and_retried(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(503)
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 1)
    await listener.stop()
    assert isinstance(probe.errors[0], SnapDogConnectionLimitError)


async def test_another_refusal_is_a_connection_error(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(500)
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 1)
    await listener.stop()
    assert type(probe.errors[0]) is SnapDogConnectionError
    assert "500" in str(probe.errors[0])


async def test_a_server_that_is_away_is_retried_with_a_growing_wait(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    _, server = ws_server
    probe = Probe()
    listener = make(session, server, probe)
    await server.close()
    listener.start()
    await probe.until(lambda: len(probe.errors) >= 3)
    await listener.stop()
    assert all(type(e) is SnapDogConnectionError for e in probe.errors)
    assert probe.connected_count == 0


async def test_a_failed_initial_read_closes_the_socket_and_tries_again(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    _, server = ws_server
    probe = Probe()
    probe.fail_connect.append(SnapDogConnectionError("REST read failed"))
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 2)
    await listener.stop()
    assert "REST read failed" in str(probe.errors[0])


async def test_a_rejected_key_during_the_initial_read_ends_the_listener(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    _, server = ws_server
    probe = Probe()
    probe.fail_connect.append(SnapDogAuthError("401"))
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: bool(probe.errors))
    await asyncio.sleep(0.1)
    assert isinstance(listener.stopped_reason, SnapDogAuthError)
    assert probe.connected_count == 1
    await listener.stop()


async def test_start_twice_runs_one_listener_and_stop_is_idempotent(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    probe = Probe()
    listener = make(session, server, probe)
    await listener.stop()  # never started
    listener.start()
    listener.start()
    await probe.until(lambda: probe.connected_count == 1)
    await asyncio.sleep(0.1)
    assert state.connections == 1
    await listener.stop()
    await listener.stop()


async def test_a_listener_can_be_started_again_after_it_stopped(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    _, server = ws_server
    probe = Probe()
    listener = make(session, server, probe)
    listener.start()
    await probe.until(lambda: probe.connected_count == 1)
    await listener.stop()
    listener.start()
    await probe.until(lambda: probe.connected_count == 2)
    await listener.stop()


async def test_a_callback_that_raises_is_logged(
    session: aiohttp.ClientSession,
    ws_server: tuple[WsServer, TestServer],
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, server = ws_server
    state.script.append(sends(VOLUME))
    probe = Probe()

    async def broken(_: Event) -> None:
        raise RuntimeError("callback bug")

    client = SnapDogClient(session, str(server.host), port=server.port or 0, api_key=API_KEY)
    listener = SnapDogListener(client, on_event=broken, on_connected=probe.on_connected)
    with caplog.at_level(logging.ERROR, logger="pysnapdog.listener"):
        listener.start()
        await asyncio.sleep(0.3)
    assert "listener stopped" in caplog.text
    assert "callback bug" in caplog.text
    await listener.stop()


async def test_a_listener_without_a_disconnect_callback_still_reconnects(
    session: aiohttp.ClientSession, ws_server: tuple[WsServer, TestServer]
) -> None:
    state, server = ws_server
    state.script.append(closes(CLOSE_TOO_SLOW))
    probe = Probe()
    client = SnapDogClient(session, str(server.host), port=server.port or 0, api_key=API_KEY)
    listener = SnapDogListener(
        client, on_event=probe.on_event, on_connected=probe.on_connected, backoff_min=0.01
    )
    listener.start()
    await probe.until(lambda: probe.connected_count == 2)
    await listener.stop()
