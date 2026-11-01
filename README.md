<div align="center">

<img src="https://raw.githubusercontent.com/SnapDogRocks/snapdog/main/assets/snapdog-logo.svg" alt="SnapDog" width="200">

**pysnapdog: async Python client for the SnapDog multi-room audio server**

Typed. Fully asynchronous. Built for Home Assistant, usable everywhere.

[![CI](https://github.com/SnapDogRocks/pysnapdog/actions/workflows/ci.yml/badge.svg)](https://github.com/SnapDogRocks/pysnapdog/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](pyproject.toml)
[![Typed](https://img.shields.io/badge/typing-strict-brightgreen.svg)](src/pysnapdog/py.typed)

</div>

---

`pysnapdog` talks to a [SnapDog](https://github.com/SnapDogRocks/snapdog) server over its REST API
and, as the library grows, over its WebSocket. It is the client library behind the SnapDog
integration for [Home Assistant](https://www.home-assistant.io), and it has no Home Assistant
dependency of its own: you hand it an `aiohttp` session and it hands you typed objects.

> [!NOTE]
> **Early development.** The library is at version 0.x. It covers every REST operation and every
> WebSocket event of the server and may still change. The plan and the checklist that defines
> "complete" are in
> [RFC HAI-0010](https://github.com/SnapDogRocks/snapdog/blob/main/docs/rfcs/0010-home-assistant-integration-build.md).
> The API may change between 0.x releases.

## Features

| | |
|---|---|
| ⚡ **Async only** | Built on `aiohttp`. You own the session, the library never opens or closes one. |
| 🧩 **Typed models** | Frozen dataclasses with `slots`. A response that lacks a field raises an error instead of producing a half-filled object. |
| 📡 **Live updates** | `SnapDogListener` keeps the WebSocket open, reconnects with a growing wait, and delivers events only after your initial read, so nothing is lost in between. |
| 📜 **Checked against the contract** | The tests run against a fake server built from the server's own `openapi.json` and `asyncapi.json`, which are pinned in [`spec/`](spec). |
| 🔐 **API key in the header** | `Authorization: Bearer`, never in a URL. TLS with or without certificate verification. |
| 🧯 **One error family** | `SnapDogConnectionError`, `SnapDogAuthError`, `SnapDogResponseError` (with `SnapDogNotFoundError`, `SnapDogUnsupportedError`, `SnapDogBusyError`), all derived from `SnapDogError`. |
| 🧪 **Strict typing** | `mypy --strict` clean, ships `py.typed`. |
| 🪶 **No extra dependencies** | `aiohttp` and nothing else. |

## Installation

```bash
pip install pysnapdog
```

Requires Python 3.14 or newer, the version Home Assistant 2026.10 runs on.

## Quick start

```python
import asyncio

import aiohttp

from pysnapdog import SnapDogClient


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = SnapDogClient(session, "snapdog.local", api_key="…")

        version = await client.version()
        print(f"{version.name} {version.version}")

        for zone in await client.zones():
            print(f"{zone.index}: {zone.name} ({zone.playback}, volume {zone.volume})")


asyncio.run(main())
```

`api_key` is only needed when the server has `api_keys` configured. For a server behind TLS pass
`tls=True`, and `verify_tls=False` for a self-signed certificate.

### Control a zone

Indexes of zones and clients start at 1, as in the server's API. Zone commands return nothing, the new
state arrives as an event. Calls on clients return the new value.

```python
await client.set_zone_volume(1, 35)  # absolute, or "+5" / "-3" for relative
await client.play_playlist(1, playlist=2)
await client.set_zone_repeat(1, RepeatMode.PLAYLIST)
await client.apply_zone_eq_preset(1, "rock")
await client.set_client_zone(3, 2)  # move client 3 into zone 2
cover = await client.zone_cover(1)  # Image(content=b"...", content_type="image/jpeg")
```

### Live updates

The server sends no initial state. `SnapDogListener` opens the socket first, lets you read the state
over REST, and only then delivers the events that arrived meanwhile, in order. It does the same again
after every reconnect.

```python
from pysnapdog import SnapDogListener, ZoneChanged, ZoneVolumeChanged

zones: dict[int, Zone] = {}


async def load() -> None:
    zones.update({z.index: z for z in await client.zones()})


async def on_event(event) -> None:
    if isinstance(event, ZoneVolumeChanged):
        print(f"zone {event.zone}: volume {event.volume}, muted {event.muted}")


listener = SnapDogListener(client, on_event=on_event, on_connected=load)
listener.start()  # from a running event loop
...
await listener.stop()
```

Events carry absolute values, never a delta. A client that falls behind is closed by the server with
code 1013, and the listener reconnects and calls `on_connected` again. A rejected API key ends the
listener, because retrying cannot help: the error is in `listener.stopped_reason`.

### Errors

```python
from pysnapdog import (
    SnapDogAuthError,
    SnapDogConnectionError,
    SnapDogError,
    SnapDogUnsupportedError,
)

try:
    eq = await client.client_eq(3)
except SnapDogAuthError:
    ...  # the key is missing or wrong
except SnapDogUnsupportedError:
    ...  # HTTP 422: the client is not a SnapDog client, so it has no EQ
except SnapDogConnectionError:
    ...  # the server is away, or the connection broke off
except SnapDogError:
    ...  # anything else the library raises
```

`SnapDogResponseError` carries `status` and the server's own message in `detail`.

## What is covered

| Area | Status |
|---|---|
| System: version, status, listeners, self-update | ✅ |
| Zones: transport, volume, mute, shuffle, repeat, seek, presence | ✅ |
| Zones: playlists, play track, playlist, Subsonic track, URL, cover | ✅ |
| Clients: volume, mute, latency, zone, name | ✅ |
| Equalizer for zones and clients, presets, speaker correction | ✅ |
| Media: playlists, tracks, covers | ✅ |
| KNX programming mode, product info, `.knxprod` download | ✅ |
| WebSocket: seven event types, reconnect, resync | ✅ |

The server has 100 REST operations. Every one is either a library call that a test exercises, or on a
short list of single-field reads that the `Zone`, `Client`, `TrackMetadata` and `ZonePlaylist` models
already carry. `scripts/check_coverage.py` compares the library with the pinned `openapi.json` and
`asyncapi.json` and fails when an operation or event is neither covered nor excluded with a reason.
CI runs it, so the gap cannot grow unnoticed.

## Development

The project uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/SnapDogRocks/pysnapdog.git
cd pysnapdog
uv sync

uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy                  # types, strict
uv run pytest --cov          # tests, coverage floor 95 %
uv run python scripts/check_coverage.py   # every operation and event of the server
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org). A local hook checks
them once you run `lefthook install` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Related projects

- [SnapDog](https://github.com/SnapDogRocks/snapdog) — the server this library talks to.
- [snapdog-homeassistant](https://github.com/SnapDogRocks/snapdog-homeassistant) — the Home
  Assistant integration built on this library (in preparation).

## License

[Apache License 2.0](LICENSE).
