# SPDX-License-Identifier: Apache-2.0
"""Keep a WebSocket to a SnapDog server open and hand its events to the caller."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aiohttp

from .client import SnapDogClient
from .events import Event, parse_event
from .exceptions import (
    SnapDogAuthError,
    SnapDogConnectionError,
    SnapDogConnectionLimitError,
    SnapDogError,
    SnapDogResponseError,
)

_LOGGER = logging.getLogger(__name__)

CLOSE_GOING_AWAY = 1001
"""The server is shutting down."""
CLOSE_TOO_SLOW = 1013
"""This client fell behind and missed events: read the state again."""

type EventCallback = Callable[[Event], Awaitable[None]]
type ConnectedCallback = Callable[[], Awaitable[None]]
type DisconnectedCallback = Callable[[SnapDogError], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _Closed:
    """Marks the end of a socket in the queue of events."""

    code: int | None


class SnapDogListener:
    """Receive the server's events, and reconnect when the socket is lost.

    The server sends no initial state. To leave no gap between reading the state and
    hearing about changes, the listener opens the socket first, calls ``on_connected``
    (where the caller reads everything over REST) and only then delivers the events that
    arrived meanwhile, in order. ``on_connected`` runs again after every reconnect.

    ``on_disconnected`` gets the reason each time the socket is lost. After a close with
    code 1013 the listener reconnects at once, because the state has to be read again
    anyway. After any other loss it waits, doubling the wait up to ``backoff_max``. A
    rejected API key ends the listener, since retrying cannot help: the error goes to
    ``on_disconnected`` and ``stopped_reason`` holds it.
    """

    def __init__(  # noqa: PLR0913 - keyword-only options of a public constructor
        self,
        client: SnapDogClient,
        *,
        on_event: EventCallback,
        on_connected: ConnectedCallback,
        on_disconnected: DisconnectedCallback | None = None,
        backoff_min: float = 1.0,
        backoff_max: float = 30.0,
        heartbeat: float = 30.0,
    ) -> None:
        """Remember what to call. Nothing connects until ``start``."""
        self._client = client
        self._on_event = on_event
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._backoff_min = backoff_min
        self._backoff_max = backoff_max
        self._heartbeat = heartbeat
        self._task: asyncio.Task[None] | None = None
        self._connected = False
        self.stopped_reason: SnapDogError | None = None

    @property
    def connected(self) -> bool:
        """Whether the socket is open and the initial state has been delivered."""
        return self._connected

    def start(self) -> None:
        """Start listening in the background. Call it from a running event loop."""
        if self._task is None or self._task.done():
            self.stopped_reason = None
            self._task = asyncio.get_running_loop().create_task(self._run())
            self._task.add_done_callback(_log_failure)

    async def stop(self) -> None:
        """Stop listening and close the socket."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        # A listener that already died of a callback error has logged it; stopping is not the
        # place to raise it a second time.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        self._connected = False

    async def _run(self) -> None:
        delay = self._backoff_min
        while True:
            try:
                resync = await self._session()
            except SnapDogAuthError as err:
                self.stopped_reason = err
                await self._lost(err)
                return
            except SnapDogError as err:
                await self._lost(err)
                resync = False
            self._connected = False
            if resync:
                delay = self._backoff_min
                continue
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff_max)

    async def _session(self) -> bool:
        """One connection. Returns True when the server asked for an immediate resync."""
        client = self._client
        try:
            ws = await client.session.ws_connect(
                client.ws_url,
                headers=client.headers,
                ssl=client.verify_tls,
                heartbeat=self._heartbeat,
            )
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise SnapDogAuthError("the server rejected the API key") from err
            if err.status == 503:
                raise SnapDogConnectionLimitError(
                    "the server serves its maximum of WebSocket connections"
                ) from err
            raise SnapDogConnectionError(f"WebSocket handshake failed: HTTP {err.status}") from err
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise SnapDogConnectionError(f"cannot open the WebSocket: {err}") from err

        queue: asyncio.Queue[Event | _Closed] = asyncio.Queue()
        reader = asyncio.get_running_loop().create_task(_read(ws, queue))
        try:
            await self._on_connected()
            self._connected = True
            while True:
                item = await queue.get()
                if isinstance(item, _Closed):
                    return await self._closed(item.code)
                await self._on_event(item)
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
            await ws.close()

    async def _closed(self, code: int | None) -> bool:
        if code == CLOSE_TOO_SLOW:
            await self._lost(SnapDogConnectionError("closed by the server: client too slow"))
            return True
        if code == CLOSE_GOING_AWAY:
            await self._lost(SnapDogConnectionError("closed by the server: shutting down"))
        else:
            await self._lost(SnapDogConnectionError(f"the WebSocket closed (code {code})"))
        return False

    async def _lost(self, reason: SnapDogError) -> None:
        self._connected = False
        _LOGGER.debug("SnapDog WebSocket lost: %s", reason)
        if self._on_disconnected is not None:
            await self._on_disconnected(reason)


async def _read(ws: aiohttp.ClientWebSocketResponse, queue: asyncio.Queue[Event | _Closed]) -> None:
    """Move messages from the socket into the queue, then mark its end."""
    async for message in ws:
        if message.type is not aiohttp.WSMsgType.TEXT:
            continue
        try:
            event = parse_event(message.json())
        except (ValueError, SnapDogResponseError) as err:
            _LOGGER.warning("ignoring an unreadable WebSocket message: %s", err)
            continue
        queue.put_nowait(event)
    queue.put_nowait(_Closed(ws.close_code))


def _log_failure(task: asyncio.Task[None]) -> None:
    """A callback that raises ends the listener; say so instead of failing silently."""
    if not task.cancelled() and (error := task.exception()) is not None:
        _LOGGER.error("the SnapDog listener stopped: %r", error, exc_info=error)
