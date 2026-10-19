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
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    """Upper bounds on the work one evaluation may do.

    The default values are provisional and will be tuned against real
    package sets before the RFC is accepted. An embedding program fixes
    its limits per release and MUST NOT take them from host settings.
    """

    max_int_bits: int = 4096
    max_str_len: int = 1_000_000
    max_collection_len: int = 1_000_000
    max_call_depth: int = 256
    max_nodes: int = 50_000_000


DEFAULT_LIMITS = Limits()


class Budget:
    """Tracks how much of each limit one evaluation has used.

    One Budget belongs to one Evaluator and is never shared.
    """

    def __init__(self, limits: Limits, filename: str) -> None:
        self.limits = limits
        self.filename = filename
        self.nodes = 0
        self.call_depth = 0

    def charge_node(self, node: ast.AST) -> None:
        """Count one evaluated node. Raises LimitExceeded past ``max_nodes``."""
        raise NotImplementedError

    def check_binop(self, op: ast.operator, left: object, right: object, node: ast.AST) -> None:
        """Reject an operation whose result would exceed a limit, before computing it.

        Covers ``**`` on ints (the result has about
        ``exponent * base.bit_length()`` bits), ``*`` on ints, and ``*`` and
        ``+`` on strings and tuples.
        """
        raise NotImplementedError

    def check_value(self, value: object, node: ast.AST) -> object:
        """Check a computed value against the size limits and return it unchanged.

        Ints are checked against ``max_int_bits``, strings against
        ``max_str_len``, and tuples, mappings and frozen sets against
        ``max_collection_len``.
        """
        raise NotImplementedError

    def enter_call(self, node: ast.AST) -> None:
        """Increase the call depth. Raises LimitExceeded past ``max_call_depth``."""
        raise NotImplementedError

    def exit_call(self) -> None:
        """Decrease the call depth after a call returns or fails."""
        raise NotImplementedError
