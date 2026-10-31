# SPDX-License-Identifier: Apache-2.0
"""Async REST client for a SnapDog server."""

from __future__ import annotations

from typing import Any

import aiohttp

from .exceptions import SnapDogAuthError, SnapDogConnectionError, SnapDogResponseError
from .models import SystemStatus, VersionInfo, Zone

DEFAULT_PORT = 5555
DEFAULT_TIMEOUT = 10.0


class SnapDogClient:
    """Talk to one SnapDog server.

    The caller owns the ``aiohttp.ClientSession`` (Home Assistant hands its own in),
    so the client never opens or closes a session itself. The API key travels in the
    ``Authorization: Bearer`` header and never in a URL.
    """

    def __init__(  # noqa: PLR0913 - keyword-only options of a public constructor
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        api_key: str | None = None,
        tls: bool = False,
        verify_tls: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Remember how to reach the server. Nothing is sent yet."""
        self._session = session
        self._base = f"{'https' if tls else 'http'}://{host}:{port}/api/v1"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._ssl = verify_tls
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def base_url(self) -> str:
        """The API root, without credentials."""
        return self._base

    async def version(self) -> VersionInfo:
        """Read ``GET /system/version``."""
        return VersionInfo.from_dict(await self._get_object("/system/version"))

    async def status(self) -> SystemStatus:
        """Read ``GET /system/status``."""
        return SystemStatus.from_dict(await self._get_object("/system/status"))

    async def zones(self) -> list[Zone]:
        """Read ``GET /zones``."""
        body = await self._get("/zones")
        if not isinstance(body, list):
            raise SnapDogResponseError("GET /zones: expected a JSON array")
        return [Zone.from_dict(_as_object(item, "GET /zones")) for item in body]

    async def zone(self, index: int) -> Zone:
        """Read ``GET /zones/{index}`` (1-based)."""
        return Zone.from_dict(await self._get_object(f"/zones/{index}"))

    async def _get_object(self, path: str) -> dict[str, Any]:
        return _as_object(await self._get(path), f"GET {path}")

    async def _get(self, path: str) -> Any:  # noqa: ANN401
        url = f"{self._base}{path}"
        try:
            async with self._session.get(
                url, headers=self._headers, ssl=self._ssl, timeout=self._timeout
            ) as response:
                if response.status == 401:
                    raise SnapDogAuthError("the server rejected the API key")
                if response.status >= 400:
                    raise SnapDogResponseError(
                        f"GET {path} failed with HTTP {response.status}", status=response.status
                    )
                try:
                    return await response.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise SnapDogResponseError(f"GET {path}: the body is not JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SnapDogConnectionError(f"cannot reach the server for GET {path}: {err}") from err


def _as_object(body: Any, what: str) -> dict[str, Any]:  # noqa: ANN401
    if not isinstance(body, dict):
        raise SnapDogResponseError(f"{what}: expected a JSON object")
    return body
