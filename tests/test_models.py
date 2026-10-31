# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from pysnapdog import SnapDogResponseError, SystemStatus, Zone

from .conftest import ZONE


def test_zone_parses_every_field() -> None:
    zone = Zone.from_dict(ZONE)
    assert zone.index == 1
    assert zone.repeat == "off"
    assert zone.icon == "🏠"


@pytest.mark.parametrize("missing", sorted(ZONE))
def test_zone_names_the_missing_field(missing: str) -> None:
    data = {k: v for k, v in ZONE.items() if k != missing}
    with pytest.raises(SnapDogResponseError, match=missing):
        Zone.from_dict(data)


def test_a_bool_is_not_an_int() -> None:
    with pytest.raises(SnapDogResponseError, match="zones"):
        SystemStatus.from_dict({"version": "1", "zones": True, "clients": 0, "radios": 0})


def test_models_are_frozen() -> None:
    zone = Zone.from_dict(ZONE)
    with pytest.raises(AttributeError):
        zone.volume = 5  # type: ignore[misc]
