# SPDX-License-Identifier: Apache-2.0
"""Read the pinned server specs and build example data from their schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SPEC_DIR = Path(__file__).resolve().parent.parent / "spec"
OPENAPI: dict[str, Any] = json.loads((SPEC_DIR / "openapi.json").read_text())
ASYNCAPI: dict[str, Any] = json.loads((SPEC_DIR / "asyncapi.json").read_text())

VERBS = ("get", "put", "post", "delete", "patch")


def operations() -> list[tuple[str, str, dict[str, Any]]]:
    """Every ``(METHOD, path template, operation)`` of the OpenAPI document."""
    return [
        (verb.upper(), path, op)
        for path, item in OPENAPI["paths"].items()
        for verb, op in item.items()
        if verb in VERBS
    ]


def resolve(schema: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``$ref``."""
    ref = schema.get("$ref")
    if ref is None:
        return schema
    node: Any = OPENAPI
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    return {**node, **{k: v for k, v in schema.items() if k != "$ref"}}


def example(schema: dict[str, Any]) -> Any:  # noqa: PLR0911
    """A value that satisfies ``schema``, with every optional property filled in."""
    schema = resolve(schema)
    if "allOf" in schema:
        merged: dict[str, Any] = {}
        for part in schema["allOf"]:
            merged.update(example(part))
        return merged
    for key in ("oneOf", "anyOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            return example(options[0])
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next(k for k in kind if k != "null")
    if kind == "object" or "properties" in schema:
        return {name: example(prop) for name, prop in schema.get("properties", {}).items()}
    if kind == "array":
        return [example(schema["items"])]
    if kind == "integer":
        return max(int(schema.get("minimum", 1)), 1)
    if kind == "number":
        return 0.5
    if kind == "boolean":
        return True
    if kind == "string":
        return "x"
    raise AssertionError(f"no example for {schema}")
