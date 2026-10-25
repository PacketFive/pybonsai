# SPDX-License-Identifier: GPL-2.0
"""Errors raised while checking and evaluating PyBonsai files.

Every error a PyBonsai file can cause derives from PyBonsaiError, so a
caller can catch one type. Each error carries the file, line and column of
the node that caused it.
"""

from __future__ import annotations

import ast


class PyBonsaiError(Exception):
    """Base class for every error caused by a PyBonsai file."""


class RejectedSyntax(SyntaxError, PyBonsaiError):
    """A construct outside the allow list, found before evaluation.

    RFC 0001 section 7.2 requires a SyntaxError that names the node type,
    file, line and column, so this class derives from SyntaxError and fills
    its ``filename``, ``lineno`` and ``offset`` fields.
    """

    @classmethod
    def at(cls, node: ast.AST, filename: str, reason: str) -> RejectedSyntax:
        """Build an error for ``node``.

        The message has the form ``"<NodeType> is not permitted: <reason>"``.
        ``lineno`` and ``col_offset`` are read from the node when it has them;
        operator and context nodes have none.
        """
        raise NotImplementedError


class EvaluationError(PyBonsaiError):
    """A failure while evaluating a file that passed the checker.

    Examples are an unknown name, a wrong argument type, a dictionary key
    that repeats only once its value is computed, an attribute used on a
    value of the wrong type, and recursion.
    """

    def __init__(
        self,
        message: str,
        filename: str,
        lineno: int | None = None,
        col_offset: int | None = None,
    ) -> None:
        """Store the message and the position it refers to."""
        super().__init__(message)
        self.message = message
        self.filename = filename
        self.lineno = lineno
        self.col_offset = col_offset

    @classmethod
    def at(cls, node: ast.AST, filename: str, message: str) -> EvaluationError:
        """Build an error positioned at ``node``."""
        raise NotImplementedError

    def __str__(self) -> str:
        """Format as ``"<file>:<line>:<column>: <message>"``."""
        raise NotImplementedError


class LimitExceeded(EvaluationError):
    """A limit from RFC 0001 section 7.7 was reached.

    ``limit`` names the Limits field that was exceeded, for example
    ``"max_int_bits"``, so tests and users can tell which one it was.
    """

    def __init__(
        self,
        limit: str,
        message: str,
        filename: str,
        lineno: int | None = None,
        col_offset: int | None = None,
    ) -> None:
        """Store the message and the position it refers to."""
        super().__init__(message, filename, lineno, col_offset)
        self.limit = limit
