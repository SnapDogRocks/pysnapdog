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

    def __init__(self, message: str, *, status: int | None = None) -> None:
        """Keep the HTTP status next to the message, when there was one."""
        super().__init__(message)
        self.status = status
