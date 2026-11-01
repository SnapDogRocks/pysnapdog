# SPDX-License-Identifier: Apache-2.0
"""What the library covers of the server's two contracts, and what it leaves out on purpose.

``problems()`` is the check behind ``scripts/check_coverage.py`` and ``test_coverage.py``:
every operation of ``spec/openapi.json`` has a library call that is tested, or an entry in
``EXCLUDED`` with a reason, and every message of ``spec/asyncapi.json`` has an event class.
"""

from __future__ import annotations

import inspect

from pysnapdog import KNOWN_EVENT_TYPES, SnapDogClient

from .spec import ASYNCAPI, operations
from .test_operations import CASES

_Z = "/api/v1/zones/{zone_index}"
_C = "/api/v1/clients/{client_index}"

_ZONE_MODEL = "a field of the Zone model, kept current by the zone events"
_TRACK_MODEL = "a field of TrackMetadata (zone_track)"
_PLAYLIST_MODEL = "a field of ZonePlaylist (zone_playlist)"
_CLIENT_MODEL = "a field of the Client model"

# "METHOD path": why there is no library call of its own.
EXCLUDED: dict[str, str] = {
    f"GET {_Z}/name": _ZONE_MODEL,
    f"GET {_Z}/icon": _ZONE_MODEL,
    f"GET {_Z}/volume": _ZONE_MODEL,
    f"GET {_Z}/mute": _ZONE_MODEL,
    f"GET {_Z}/playback": _ZONE_MODEL,
    f"GET {_Z}/shuffle": _ZONE_MODEL,
    f"GET {_Z}/repeat": _ZONE_MODEL,
    f"GET {_Z}/presence": _ZONE_MODEL,
    f"GET {_Z}/presence/enable": _ZONE_MODEL,
    f"GET {_Z}/presence/timer": _ZONE_MODEL,
    f"GET {_Z}/track": _PLAYLIST_MODEL,
    f"GET {_Z}/playlist": _PLAYLIST_MODEL,
    f"GET {_Z}/playlist/count": _PLAYLIST_MODEL,
    f"GET {_Z}/playlist/name": _PLAYLIST_MODEL,
    f"GET {_Z}/track/title": _TRACK_MODEL,
    f"GET {_Z}/track/artist": _TRACK_MODEL,
    f"GET {_Z}/track/album": _TRACK_MODEL,
    f"GET {_Z}/track/duration": _TRACK_MODEL,
    f"GET {_Z}/track/position": _TRACK_MODEL,
    f"GET {_Z}/track/progress": "derived from position and duration of TrackMetadata",
    f"GET {_Z}/track/playing": "the playback field of the Zone model",
    f"GET {_C}/name": _CLIENT_MODEL,
    f"GET {_C}/icon": _CLIENT_MODEL,
    f"GET {_C}/volume": _CLIENT_MODEL,
    f"GET {_C}/mute": _CLIENT_MODEL,
    f"GET {_C}/connected": _CLIENT_MODEL,
    f"GET {_C}/zone": _CLIENT_MODEL,
}

# Events the library parses but a client has nothing to do with, with the reason.
EXCLUDED_EVENTS: dict[str, str] = {
    "zone_progress": "reserved: the server declares it and never sends it",
}

# Public methods of the client that are not an API operation.
NOT_OPERATIONS = frozenset({"base_url", "ws_url", "session", "headers", "verify_tls"})


def _public_methods() -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(SnapDogClient)
        if not name.startswith("_")
        and (inspect.iscoroutinefunction(member) or isinstance(member, property))
    }


def problems() -> list[str]:
    """Everything that does not add up. An empty list means the coverage is complete."""
    found: list[str] = []
    spec_ops = {f"{verb} {path}" for verb, path, _ in operations()}
    covered = {case.operation for case in CASES}

    for key in sorted(spec_ops - covered - set(EXCLUDED)):
        found.append(f"operation without a library call or an exclusion: {key}")
    for key in sorted(covered - spec_ops):
        found.append(f"tested call for an operation that is not in the spec: {key}")
    for key in sorted(set(EXCLUDED) - spec_ops):
        found.append(f"exclusion for an operation that is not in the spec: {key}")
    for key in sorted(set(EXCLUDED) & covered):
        found.append(f"operation is both covered and excluded: {key}")

    messages = set(ASYNCAPI["components"]["messages"])
    for name in sorted(messages - KNOWN_EVENT_TYPES):
        found.append(f"event without an event class: {name}")
    for name in sorted(KNOWN_EVENT_TYPES - messages):
        found.append(f"event class for a message that is not in the spec: {name}")
    for name in sorted(set(EXCLUDED_EVENTS) - messages):
        found.append(f"exclusion for an event that is not in the spec: {name}")
    return found
