# SPDX-License-Identifier: GPL-2.0
"""Parsing PyBonsai source into a syntax tree (RFC 0001 section 7.1).

This is the only place where Python's own parser is used. Nothing in
PyBonsai never passes source text to ``eval``, ``exec`` or ``compile``.
"""

from __future__ import annotations

import ast

PYTHON_BASELINE: tuple[int, int] = (3, 12)


def require_supported_python() -> None:
    """Fail early when the running interpreter is older than the baseline.

    Raises RuntimeError naming the required and the running version.
    """
    raise NotImplementedError


def parse(source: str, filename: str) -> ast.Module:
    """Parse ``source`` with the Python 3.12 grammar.

    Calls ``ast.parse(source, filename=filename, mode="exec",
    feature_version=PYTHON_BASELINE)``. A SyntaxError from the parser is
    re-raised as RejectedSyntax with the same position, so callers handle a
    single error type. The tree is returned unchecked; pass it to
    checker.check before evaluating it.
    """
    raise NotImplementedError
