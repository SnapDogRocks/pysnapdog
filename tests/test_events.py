# SPDX-License-Identifier: Apache-2.0
"""The events against the messages of the pinned AsyncAPI document."""

from __future__ import annotations

from typing import Any

import pytest

from pysnapdog import (
    KNOWN_EVENT_TYPES,
    ClientStateChanged,
    EqConfig,
    PlaybackError,
    RepeatMode,
    SnapDogResponseError,
    UnknownEvent,
    ZoneChanged,
    ZoneEqChanged,
    ZonePresenceChanged,
    ZoneProgress,
    ZoneVolumeChanged,
    parse_event,
)

from .spec import ASYNCAPI, example

CLASSES = {
    "zone_changed": ZoneChanged,
    "zone_volume_changed": ZoneVolumeChanged,
    "zone_progress": ZoneProgress,
    "client_state_changed": ClientStateChanged,
    "zone_eq_changed": ZoneEqChanged,
    "zone_presence_changed": ZonePresenceChanged,
    "playback_error": PlaybackError,
}
MESSAGES: dict[str, Any] = ASYNCAPI["components"]["messages"]


def payload(name: str) -> dict[str, Any]:
    return example(MESSAGES[name]["payload"])  # type: ignore[no-any-return]


def required(name: str) -> list[str]:
    schema = MESSAGES[name]["payload"]
    parts = schema.get("allOf", [schema])
    return [field for part in parts for field in part.get("required", [])]


def test_every_message_of_the_spec_has_a_class() -> None:
    assert set(MESSAGES) == set(CLASSES) == KNOWN_EVENT_TYPES


@pytest.mark.parametrize("name", CLASSES)
def test_an_event_is_what_the_spec_describes(name: str) -> None:
    event = parse_event(payload(name))
    assert type(event) is CLASSES[name]


@pytest.mark.parametrize(
    ("name", "field"),
    [(n, f) for n in CLASSES for f in required(n) if f not in ("type", "bands", "enabled")],
)
def test_a_missing_field_is_named(name: str, field: str) -> None:
    data = {k: v for k, v in payload(name).items() if k != field}
    with pytest.raises(SnapDogResponseError, match=field):
        parse_event(data)


def test_a_zone_changed_event_carries_its_values() -> None:
    event = parse_event({**payload("zone_changed"), "repeat": "track", "volume": 33, "title": "T"})
    assert isinstance(event, ZoneChanged)
    assert (event.repeat, event.volume, event.title) == (RepeatMode.TRACK, 33, "T")


def test_the_eq_config_is_flattened_into_the_event() -> None:
    event = parse_event(payload("zone_eq_changed"))
    assert isinstance(event, ZoneEqChanged)
    assert isinstance(event.config, EqConfig)
    assert event.config.bands


def test_an_unknown_type_is_kept_not_refused() -> None:
    event = parse_event({"type": "zone_party_started", "zone": 1})
    assert event == UnknownEvent(
        type="zone_party_started", data={"type": "zone_party_started", "zone": 1}
    )


@pytest.mark.parametrize("data", [[], "x", 5, {"zone": 1}, {"type": 3}])
def test_a_message_without_a_type_is_refused(data: Any) -> None:
    with pytest.raises(SnapDogResponseError, match="'type'"):
        parse_event(data)
