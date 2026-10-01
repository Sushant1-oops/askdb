"""Domain errors shared across services. Routers map these to HTTP status codes."""

from __future__ import annotations


class AskDBError(Exception):
    """Base class for expected, user-facing errors."""


class NotFoundError(AskDBError):
    """A connection, table or other resource does not exist."""


class BadRequestError(AskDBError):
    """The request is well-formed but cannot be honoured."""


class QueryExecutionError(AskDBError):
    """The database rejected or failed to run a query."""


class QueryTimeoutError(QueryExecutionError):
    """The query exceeded the configured time limit."""


class LLMUnavailableError(AskDBError):
    """No LLM could be reached (missing key, network, quota, all models failed)."""
