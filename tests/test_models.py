# SPDX-License-Identifier: Apache-2.0
"""The models against the schemas of the pinned spec."""

from __future__ import annotations

from typing import Any

import pytest

from pysnapdog import (
    Client,
    EqBand,
    EqConfig,
    EqPreset,
    Listener,
    MediaTrack,
    Playlist,
    PlaylistDetails,
    ProductInfo,
    RepeatMode,
    SnapDogResponseError,
    SystemStatus,
    TrackMetadata,
    UpdateConfig,
    UpdateProgress,
    UpdateStatus,
    VersionInfo,
    Zone,
    ZonePlaylist,
)

from .spec import OPENAPI, example

MODELS: dict[str, Any] = {
    "VersionInfo": VersionInfo,
    "SystemStatus": SystemStatus,
    "Row": Listener,
    "ZoneInfo": Zone,
    "ClientInfo": Client,
    "ZoneTrackMetadata": TrackMetadata,
    "ZonePlaylistInfo": ZonePlaylist,
    "PlaylistInfo": Playlist,
    "PlaylistDetails": PlaylistDetails,
    "MediaTrackInfo": MediaTrack,
    "EqBand": EqBand,
    "EqConfig": EqConfig,
    "EqPreset": EqPreset,
    "UpdateProgress": UpdateProgress,
    "UpdateStatus": UpdateStatus,
    "ProductInfo": ProductInfo,
}


def sample(name: str) -> dict[str, Any]:
    return example({"$ref": f"#/components/schemas/{name}"})  # type: ignore[no-any-return]


# The server still lists these as required. The library accepts payloads of older servers
# that lack them, so each has a test of its own below.
TOLERATED = {
    ("PlaylistInfo", "id"),
    ("PlaylistInfo", "index"),
    ("PlaylistInfo", "playlist_id"),
    ("PlaylistDetails", "id"),
    ("PlaylistDetails", "index"),
    ("PlaylistDetails", "playlist_id"),
}
REQUIRED = [
    (name, field)
    for name in MODELS
    for field in OPENAPI["components"]["schemas"][name].get("required", [])
    if (name, field) not in TOLERATED
]
OPTIONAL = [
    (name, field)
    for name in MODELS
    for field in OPENAPI["components"]["schemas"][name].get("properties", {})
    if field not in OPENAPI["components"]["schemas"][name].get("required", [])
]


@pytest.mark.parametrize("name", MODELS)
def test_a_model_parses_what_the_spec_describes(name: str) -> None:
    assert MODELS[name].from_dict(sample(name)) is not None


@pytest.mark.parametrize(("name", "field"), REQUIRED)
def test_a_missing_required_field_is_named(name: str, field: str) -> None:
    data = {k: v for k, v in sample(name).items() if k != field}
    with pytest.raises(SnapDogResponseError, match=field):
        MODELS[name].from_dict(data)


@pytest.mark.parametrize(("name", "field"), OPTIONAL)
def test_an_optional_field_may_be_absent_or_null(name: str, field: str) -> None:
    absent = {k: v for k, v in sample(name).items() if k != field}
    null = {**sample(name), field: None}
    for data in (absent, null):
        MODELS[name].from_dict(data)


@pytest.mark.parametrize("name", ["PlaylistInfo", "PlaylistDetails"])
def test_a_playlist_parses_without_the_deprecated_id(name: str) -> None:
    data = {k: v for k, v in sample(name).items() if k != "id"}
    data["index"] = 4
    data["playlist_id"] = "subsonic:42"
    model = MODELS[name].from_dict(data)
    assert (model.index, model.playlist_id) == (4, "subsonic:42")


@pytest.mark.parametrize("name", ["PlaylistInfo", "PlaylistDetails"])
def test_index_wins_over_id_and_id_reads_as_index(name: str) -> None:
    model = MODELS[name].from_dict({**sample(name), "id": 9, "index": 4})
    assert model.index == 4
    assert model.id == 4


@pytest.mark.parametrize("name", ["PlaylistInfo", "PlaylistDetails"])
def test_a_playlist_of_an_older_server_falls_back_to_id(name: str) -> None:
    data = {k: v for k, v in sample(name).items() if k not in ("index", "playlist_id")}
    data["id"] = 7
    model = MODELS[name].from_dict(data)
    assert (model.index, model.playlist_id) == (7, None)


@pytest.mark.parametrize("name", ["PlaylistInfo", "PlaylistDetails"])
def test_a_playlist_with_neither_index_nor_id_is_refused(name: str) -> None:
    data = {k: v for k, v in sample(name).items() if k not in ("index", "id")}
    with pytest.raises(SnapDogResponseError, match="index"):
        MODELS[name].from_dict(data)


def test_the_zone_models_carry_the_playlist_id() -> None:
    track = TrackMetadata.from_dict({**sample("ZoneTrackMetadata"), "playlist_id": "snapdog:radio"})
    assert track.playlist_id == "snapdog:radio"
    info = ZonePlaylist.from_dict({**sample("ZonePlaylistInfo"), "playlist_id": "subsonic:1"})
    assert info.playlist_id == "subsonic:1"
    assert ZonePlaylist.from_dict({}).playlist_id is None


def test_a_bool_is_not_an_int() -> None:
    with pytest.raises(SnapDogResponseError, match="zones"):
        SystemStatus.from_dict({"version": "1", "zones": True, "clients": 0, "radios": 0})


def test_a_bool_is_not_a_number() -> None:
    data = {**sample("EqBand"), "gain": True}
    with pytest.raises(SnapDogResponseError, match="gain"):
        EqBand.from_dict(data)


def test_an_integer_is_a_number() -> None:
    assert EqBand.from_dict({**sample("EqBand"), "freq": 1000}).freq == 1000.0


def test_an_unknown_enum_value_is_refused() -> None:
    with pytest.raises(SnapDogResponseError, match="'one'"):
        Zone.from_dict({**sample("ZoneInfo"), "repeat": "one"})
    with pytest.raises(SnapDogResponseError, match="'bell'"):
        EqBand.from_dict({**sample("EqBand"), "type": "bell"})


def test_a_field_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(SnapDogResponseError, match="title"):
        TrackMetadata.from_dict({**sample("ZoneTrackMetadata"), "title": 5})
    with pytest.raises(SnapDogResponseError, match="year"):
        TrackMetadata.from_dict({**sample("ZoneTrackMetadata"), "year": "1999"})


def test_models_are_frozen() -> None:
    zone = Zone.from_dict(sample("ZoneInfo"))
    with pytest.raises(AttributeError):
        zone.volume = 5  # type: ignore[misc]


def test_an_eq_config_round_trips() -> None:
    data = sample("EqConfig")
    config = EqConfig.from_dict(data)
    assert EqConfig.from_dict(config.to_dict()) == config
    assert config.to_dict()["bands"] == [b.to_dict() for b in config.bands]


def test_an_eq_config_without_a_preset_omits_it() -> None:
    config = EqConfig(enabled=False, bands=())
    assert config.to_dict() == {"enabled": False, "bands": []}


def test_an_eq_config_needs_objects_as_bands() -> None:
    with pytest.raises(SnapDogResponseError, match="expected a JSON object"):
        EqConfig.from_dict({"enabled": True, "bands": [1]})


def test_the_update_status_carries_its_progress() -> None:
    status = UpdateStatus.from_dict({**sample("UpdateStatus"), "progress": {"phase": "download"}})
    assert status.progress == UpdateProgress(phase="download", detail=None)
    assert UpdateStatus.from_dict({**sample("UpdateStatus"), "progress": None}).progress is None
    with pytest.raises(SnapDogResponseError, match="expected a JSON object"):
        UpdateStatus.from_dict({**sample("UpdateStatus"), "progress": "x"})


def test_the_update_config_uses_the_servers_spelling() -> None:
    config = UpdateConfig("auto", "03:00", "UTC")
    assert config.to_dict() == {"mode": "auto", "maintenanceTime": "03:00", "timezone": "UTC"}


def test_repeat_modes_are_strings() -> None:
    assert RepeatMode.TRACK.value == "track"
    assert str(RepeatMode("playlist")) == "playlist"
