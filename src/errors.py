# SPDX-License-Identifier: GPL-2.0
"""Errors raised while checking and evaluating PyBonsai files.

Every error a PyBonsai file can cause derives from PyBonsaiError, so a
caller can catch one type. Each error carries the file, line and column of
the node that caused it.
"""

from __future__ import annotations

import ast


def _position(node: ast.AST) -> tuple[int | None, int | None]:
    """Return the node's ``(lineno, col_offset)``, with None for what it lacks.

    Operator and context nodes such as ``ast.Add`` carry no position.
    """
    return getattr(node, "lineno", None), getattr(node, "col_offset", None)


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
        operator and context nodes have none. SyntaxError counts columns
        from 1, so ``offset`` is ``col_offset + 1``.
        """
        lineno, col_offset = _position(node)
        offset = None if col_offset is None else col_offset + 1
        message = f"{type(node).__name__} is not permitted: {reason}"
        return cls(message, (filename, lineno, offset, None))


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
        """Build an error positioned at ``node``.

        LimitExceeded takes the limit name first, so it is built with its
        constructor and ``_position(node)`` instead of with this method.
        """
        lineno, col_offset = _position(node)
        return cls(message, filename, lineno, col_offset)

    def __str__(self) -> str:
        """Format as ``"<file>:<line>:<column>: <message>"``.

        The column counts from 1, as editors and SyntaxError do, while
        ``col_offset`` keeps the 0-based value from the syntax tree. Parts of
        the position that are unknown are left out.
        """
        if self.lineno is None:
            return f"{self.filename}: {self.message}"
        if self.col_offset is None:
            return f"{self.filename}:{self.lineno}: {self.message}"
        return f"{self.filename}:{self.lineno}:{self.col_offset + 1}: {self.message}"


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
