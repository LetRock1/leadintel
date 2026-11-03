"""
Domain errors. Services raise these instead of HTTP exceptions, so they stay usable outside a web request
(the scheduler, the history generator, tests); ``app.main`` turns each one into a JSON response with its status
code and ``{"detail": message}``, the same shape FastAPI uses for its own errors.
"""

from __future__ import annotations


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(AppError):
    status_code = 400


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Unavailable(AppError):
    status_code = 503
