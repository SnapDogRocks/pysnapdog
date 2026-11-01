# SPDX-License-Identifier: Apache-2.0
"""Exceptions raised by pysnapdog."""

from __future__ import annotations


class SnapDogError(Exception):
    """Base class of every error pysnapdog raises."""


class SnapDogConnectionError(SnapDogError):
    """The server could not be reached, or the connection broke off."""


class SnapDogAuthError(SnapDogError):
    """The server answered 401: the API key is missing or wrong."""


class SnapDogResponseError(SnapDogError):
    """The server answered with an error status, or with a body that is not understood."""

    def __init__(
        self, message: str, *, status: int | None = None, detail: str | None = None
    ) -> None:
        """Keep the HTTP status and the server's own message next to ours, when there were any."""
        super().__init__(message)
        self.status = status
        self.detail = detail


class SnapDogNotFoundError(SnapDogResponseError):
    """The server answered 404: the zone, client, playlist, track or cover does not exist."""


class SnapDogUnsupportedError(SnapDogResponseError):
    """The server answered 422: the call does not apply, for example EQ on a non-SnapDog client."""


class SnapDogBusyError(SnapDogResponseError):
    """The server answered 503: a service it depends on is not configured or not reachable."""


class SnapDogConnectionLimitError(SnapDogConnectionError):
    """The server refused the WebSocket because it already serves its maximum of connections."""
