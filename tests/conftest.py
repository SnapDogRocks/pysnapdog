# SPDX-License-Identifier: Apache-2.0
"""A fake SnapDog server that is built from the pinned ``spec/openapi.json``.

Every operation of the spec is a route. A request body is validated against the schema
the spec gives it, and the answer is generated from the success response schema, so the
library is tested against the contract and not against what it expects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import aiohttp
import jsonschema
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from .spec import OPENAPI, example, operations

API_KEY = "s3cret"

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@dataclass
class Call:
    """One request the fake server has seen."""

    method: str
    path: str
    body: Any
    headers: dict[str, str]


@dataclass
class Record:
    """What the handlers write and the tests read."""

    calls: list[Call] = field(default_factory=list)
    # Replace the generated answer of one operation: ("PUT", "/api/v1/zones/{zone_index}/volume").
    overrides: dict[tuple[str, str], web.StreamResponse] = field(default_factory=dict)
    # Schema violations in request bodies, which the handlers answer with 400.
    violations: list[str] = field(default_factory=list)


@dataclass
class Fake:
    """The server under test."""

    server: TestServer
    host: str
    port: int
    record: Record

    @property
    def calls(self) -> list[Call]:
        """Every request seen so far, the rejected ones included."""
        return self.record.calls

    @property
    def last(self) -> Call:
        """The most recent request."""
        return self.record.calls[-1]

    @property
    def overrides(self) -> dict[tuple[str, str], web.StreamResponse]:
        """Fixed answers that replace the generated ones."""
        return self.record.overrides

    @property
    def violations(self) -> list[str]:
        """Request bodies that broke the spec."""
        return self.record.violations


def _validator(schema: dict[str, Any]) -> jsonschema.Draft202012Validator:
    # The components travel with the schema so that local $refs resolve.
    return jsonschema.Draft202012Validator({**schema, "components": OPENAPI["components"]})


def _make_handler(record: Record, method: str, template: str, operation: dict[str, Any]) -> Handler:
    request_body = operation.get("requestBody", {}).get("content", {})
    request_schema = request_body.get("application/json", {}).get("schema")
    success: dict[str, Any] = next(
        (r for code, r in operation["responses"].items() if code.startswith("2")), {}
    )
    content = success.get("content", {})

    async def handler(request: web.Request) -> web.StreamResponse:
        body: Any = await request.json() if request.can_read_body else None
        record.calls.append(Call(method, request.raw_path, body, dict(request.headers)))

        if request_schema is not None:
            errors = list(_validator(request_schema).iter_errors(body))
            if errors:
                record.violations.append(f"{method} {template}: {errors[0].message}")
                return web.json_response(
                    {"error": "bad_request", "message": errors[0].message}, status=400
                )
        elif body is not None:
            record.violations.append(f"{method} {template}: the spec has no request body")

        override = record.overrides.get((method, template))
        if override is not None:
            return override
        if "application/json" in content:
            return web.json_response(example(content["application/json"]["schema"]))
        if any(kind.startswith("image/") for kind in content):
            return web.Response(body=b"\x89PNG-bytes", content_type="image/png")
        return web.Response(status=200)

    return handler


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
async def fake() -> AsyncIterator[Fake]:
    record = Record()

    @web.middleware
    async def auth(request: web.Request, handler: Handler) -> web.StreamResponse:
        if request.headers.get("Authorization") != f"Bearer {API_KEY}":
            record.calls.append(Call(request.method, request.raw_path, None, dict(request.headers)))
            return web.Response(status=401, text="Invalid or missing API key")
        return await handler(request)

    app = web.Application(middlewares=[auth])
    for method, template, operation in operations():
        # The spec writes {zone_index}; aiohttp accepts the same placeholder syntax.
        app.router.add_route(method, template, _make_handler(record, method, template, operation))

    server = TestServer(app)
    await server.start_server()
    assert server.port is not None
    # Read once: a closed TestServer forgets its port.
    try:
        yield Fake(server=server, host=str(server.host), port=server.port, record=record)
    finally:
        await server.close()
