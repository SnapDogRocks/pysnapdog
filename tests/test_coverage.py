# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import inspect

from pysnapdog import SnapDogClient

from .coverage import EXCLUDED, NOT_OPERATIONS, problems
from .spec import ASYNCAPI, OPENAPI
from .test_operations import CASES


def test_every_operation_and_event_of_the_spec_is_covered_or_excluded() -> None:
    assert problems() == []


def test_every_public_call_of_the_client_is_tested() -> None:
    tested: set[str] = set()
    for case in CASES:
        source = inspect.getsource(case.call)
        tested.update(
            name for name, _ in inspect.getmembers(SnapDogClient) if f".{name}(" in source
        )
    untested = {
        name
        for name, member in inspect.getmembers(SnapDogClient)
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    } - tested
    assert untested == set(), f"library calls no case exercises: {sorted(untested)}"
    assert NOT_OPERATIONS.isdisjoint(tested)


def test_the_spec_is_the_one_the_library_was_written_for() -> None:
    assert OPENAPI["openapi"] == "3.1.0"
    assert ASYNCAPI["asyncapi"] == "3.0.0"
    # The exclusions are a minority: most of the API has a call of its own.
    assert len(EXCLUDED) < len(CASES)
