<div align="center">

<img src="https://raw.githubusercontent.com/SnapDogRocks/snapdog/main/assets/snapdog-logo.svg" alt="SnapDog" width="160">

# pysnapdog

**Async Python client for the SnapDog multi-room audio server**

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
> **Early development.** The library is at version 0.x and covers the read side of the system
> and zone endpoints so far. The plan and the checklist that defines "complete" are in
> [RFC HAI-0010](https://github.com/SnapDogRocks/snapdog/blob/main/docs/rfcs/0010-home-assistant-integration-build.md).
> The API may change between 0.x releases.

## Features

| | |
|---|---|
| ⚡ **Async only** | Built on `aiohttp`. You own the session, the library never opens or closes one. |
| 🧩 **Typed models** | Frozen dataclasses with `slots`. A response that lacks a field raises an error instead of producing a half-filled object. |
| 🔐 **API key in the header** | `Authorization: Bearer`, never in a URL. TLS with or without certificate verification. |
| 🧯 **One error family** | `SnapDogConnectionError`, `SnapDogAuthError`, `SnapDogResponseError`, all derived from `SnapDogError`. |
| 🧪 **Strict typing** | `mypy --strict` clean, ships `py.typed`. |
| 🪶 **No extra dependencies** | `aiohttp` and nothing else. |

## Installation

```bash
pip install pysnapdog
```

> [!IMPORTANT]
> Not on PyPI yet. Until the first release, install from a checkout:
> `uv pip install -e .` or `pip install -e .`.

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

### Errors

```python
from pysnapdog import SnapDogAuthError, SnapDogConnectionError, SnapDogError

try:
    zones = await client.zones()
except SnapDogAuthError:
    ...  # the key is missing or wrong
except SnapDogConnectionError:
    ...  # the server is away, or the connection broke off
except SnapDogError:
    ...  # anything else the library raises
```

## What is covered

| Area | Status |
|---|---|
| System: version, status | ✅ |
| Zones: list, details | ✅ |
| Zone control: play, pause, volume, mute, shuffle, repeat, seek | planned |
| Playlists and media browsing | planned |
| Clients: volume, mute, latency, zone, EQ | planned |
| WebSocket push with reconnect | planned |
| Presence, EQ, speaker correction, updates, KNX | planned |

Every REST operation and every WebSocket event of the server must end up here or in an explicit
exclusion list. A CI check that compares the library against the server's `openapi.json` is part
of the plan, so the gap cannot grow unnoticed.

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
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org). A local hook checks
them once you run `lefthook install` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Related projects

- [SnapDog](https://github.com/SnapDogRocks/snapdog) — the server this library talks to.
- [snapdog-homeassistant](https://github.com/SnapDogRocks/snapdog-homeassistant) — the Home
  Assistant integration built on this library (in preparation).

## License

[Apache License 2.0](LICENSE).
