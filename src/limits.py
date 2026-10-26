# SPDX-License-Identifier: GPL-2.0
"""Evaluation limits (RFC 0001 section 7.7).

The limits are fixed by the release of the program that embeds PyBonsai,
not by local settings, so a file succeeds or fails identically on every
machine. Values that would exceed a
limit are rejected before they are computed where possible, because
``10 ** 10 ** 8`` exhausts memory before any check after the fact can run.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import LimitExceeded, _position


class LimitReached(Exception):  # noqa: N818
    """Raised by a builtin that refuses a result larger than a limit.

    A builtin has no syntax node, so the evaluator catches this and raises
    LimitExceeded at the call instead. ``limit`` names the Limits field.
    """

    def __init__(self, limit: str, message: str) -> None:
        """Store the limit name and the message."""
        super().__init__(message)
        self.limit = limit
        self.message = message


@dataclass(frozen=True)
class Limits:
    """Upper bounds on the work one evaluation may do.

    The default values are provisional and will be tuned against real
    package sets before the RFC is accepted. An embedding program fixes
    its limits per release and MUST NOT take them from host settings.

    ``max_depth`` bounds how deeply evaluation nests, counting expressions
    and statements across function calls. With ``max_call_depth`` it keeps
    the evaluator well inside the Python interpreter's own recursion limit,
    so a deep file fails with LimitExceeded and never with RecursionError.
    """

    max_int_bits: int = 4096
    max_str_len: int = 1_000_000
    max_collection_len: int = 1_000_000
    max_call_depth: int = 64
    max_depth: int = 100
    max_nodes: int = 50_000_000


DEFAULT_LIMITS = Limits()

_SIZED = (tuple, frozenset)


def _int_bits(value: int) -> int:
    return abs(value).bit_length()


class Budget:
    """Tracks how much of each limit one evaluation has used.

    One Budget belongs to one Evaluator and is never shared.
    """

    def __init__(self, limits: Limits, filename: str) -> None:
        """Start an empty budget for ``limits``, reporting errors against ``filename``."""
        self.limits = limits
        self.filename = filename
        self.nodes = 0
        self.call_depth = 0
        self.depth = 0

    def exceeded(self, limit: str, message: str, node: ast.AST) -> LimitExceeded:
        """Return a LimitExceeded for ``limit`` positioned at ``node``; the caller raises it."""
        lineno, col_offset = _position(node)
        return LimitExceeded(limit, message, self.filename, lineno, col_offset)

    def charge_node(self, node: ast.AST) -> None:
        """Count one evaluated node. Raises LimitExceeded past ``max_nodes``."""
        self.nodes += 1
        if self.nodes > self.limits.max_nodes:
            raise self.exceeded(
                "max_nodes", f"more than {self.limits.max_nodes} nodes evaluated", node
            )

    def enter(self, node: ast.AST) -> None:
        """Increase the nesting depth. Raises LimitExceeded past ``max_depth``.

        The caller decreases ``depth`` again when the node is done. A call
        saves and restores ``depth`` itself, so an error or a ``return``
        that skips the decrease does not leave the count wrong.
        """
        self.depth += 1
        if self.depth > self.limits.max_depth:
            raise self.exceeded(
                "max_depth", f"evaluation nested more than {self.limits.max_depth} deep", node
            )

    def check_binop(self, op: ast.operator, left: object, right: object, node: ast.AST) -> None:
        """Reject an operation whose result would exceed a limit, before computing it.

        Covers ``**`` and ``*`` on ints, using a lower bound on the bits of
        the result, and ``*`` and ``+`` on strings and tuples, using the
        exact length of the result.
        """
        limits = self.limits
        if isinstance(op, ast.Pow) and type(left) in (int, bool) and type(right) in (int, bool):
            assert isinstance(left, int) and isinstance(right, int)  # noqa: S101
            if right > 1 and abs(left) > 1:
                bits = (_int_bits(left) - 1) * right + 1
                if bits > limits.max_int_bits:
                    raise self.exceeded(
                        "max_int_bits", f"integer larger than {limits.max_int_bits} bits", node
                    )
            return
        if isinstance(op, ast.Mult):
            if type(left) in (int, bool) and type(right) in (int, bool):
                assert isinstance(left, int) and isinstance(right, int)  # noqa: S101
                if left and right:
                    bits = _int_bits(left) + _int_bits(right) - 1
                    if bits > limits.max_int_bits:
                        raise self.exceeded(
                            "max_int_bits", f"integer larger than {limits.max_int_bits} bits", node
                        )
                return
            sequence, count = (left, right) if type(right) in (int, bool) else (right, left)
            if type(count) in (int, bool) and type(sequence) in (str, tuple):
                assert isinstance(count, int)  # noqa: S101
                assert isinstance(sequence, (str, tuple))  # noqa: S101
                self._check_length(sequence, len(sequence) * max(count, 0), node)
            return
        if isinstance(op, ast.Add) and type(left) is type(right) and type(left) in (str, tuple):
            assert isinstance(left, (str, tuple)) and isinstance(right, (str, tuple))  # noqa: S101
            self._check_length(left, len(left) + len(right), node)

    def _check_length(self, kind: object, length: int, node: ast.AST) -> None:
        if type(kind) is str:
            if length > self.limits.max_str_len:
                raise self.exceeded(
                    "max_str_len", f"string longer than {self.limits.max_str_len}", node
                )
        elif length > self.limits.max_collection_len:
            raise self.exceeded(
                "max_collection_len",
                f"collection longer than {self.limits.max_collection_len}",
                node,
            )

    def check_value(self, value: object, node: ast.AST) -> object:
        """Check a computed value against the size limits and return it unchanged.

        Ints are checked against ``max_int_bits``, strings against
        ``max_str_len``, and tuples, mappings and frozen sets against
        ``max_collection_len``.
        """
        kind = type(value)
        if kind is int:
            assert isinstance(value, int)  # noqa: S101
            if _int_bits(value) > self.limits.max_int_bits:
                raise self.exceeded(
                    "max_int_bits", f"integer larger than {self.limits.max_int_bits} bits", node
                )
        elif kind is str or kind in _SIZED or isinstance(value, Mapping):
            self._check_length(value, len(value), node)  # type: ignore[arg-type]
        return value

    def enter_call(self, node: ast.AST) -> None:
        """Increase the call depth. Raises LimitExceeded past ``max_call_depth``."""
        self.call_depth += 1
        if self.call_depth > self.limits.max_call_depth:
            self.call_depth -= 1
            raise self.exceeded(
                "max_call_depth", f"calls nested more than {self.limits.max_call_depth} deep", node
            )

    def exit_call(self) -> None:
        """Decrease the call depth after a call returns or fails."""
        self.call_depth -= 1
