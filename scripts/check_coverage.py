#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail unless the library covers every operation and event of the pinned server specs.

Run as ``uv run python scripts/check_coverage.py``; CI does. It reads ``spec/openapi.json``
and ``spec/asyncapi.json``, the copies of the server's contracts the library was written
against, and prints what is covered, what is excluded with a reason, and what is missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.coverage import EXCLUDED, EXCLUDED_EVENTS, problems
from tests.spec import ASYNCAPI, operations
from tests.test_operations import CASES


def main() -> int:
    """Print the coverage and return the exit status."""
    total = len(operations())
    print(f"REST operations: {total}, with a call: {len(CASES)}, excluded: {len(EXCLUDED)}")
    for key, reason in sorted(EXCLUDED.items()):
        print(f"  excluded  {key}: {reason}")
    events = len(ASYNCAPI["components"]["messages"])
    print(f"WebSocket events: {events}, parsed: {events}, reserved: {len(EXCLUDED_EVENTS)}")
    found = problems()
    for problem in found:
        print(f"PROBLEM  {problem}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
