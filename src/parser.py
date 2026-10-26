# SPDX-License-Identifier: GPL-2.0
"""Parsing PyBonsai source into a syntax tree (RFC 0001 section 7.1).

This is the only place where Python's own parser is used. PyBonsai never
passes source text to ``eval``, ``exec`` or ``compile``.
"""

from __future__ import annotations

import ast
import sys

from .errors import RejectedSyntax

PYTHON_BASELINE: tuple[int, int] = (3, 12)

# The deepest syntax tree accepted. The checker and evaluator walk the tree
# recursively, so this bound keeps them inside the interpreter's own
# recursion limit. Real configuration files stay far below it.
MAX_TREE_DEPTH = 200


def require_supported_python() -> None:
    """Fail early when the running interpreter is older than the baseline.

    Raises RuntimeError naming the required and the running version.
    """
    if sys.version_info[:2] < PYTHON_BASELINE:
        required = ".".join(map(str, PYTHON_BASELINE))
        running = ".".join(map(str, sys.version_info[:2]))
        raise RuntimeError(f"PyBonsai needs Python {required} or later, not {running}")


def parse(source: str, filename: str) -> ast.Module:
    """Parse ``source`` with the Python 3.12 grammar.

    Calls ``ast.parse(source, filename=filename, mode="exec",
    feature_version=PYTHON_BASELINE)``. A SyntaxError from the parser is
    re-raised as RejectedSyntax with the same position, so callers handle a
    single error type. Source too deeply nested for the parser, or a tree
    deeper than MAX_TREE_DEPTH, is also RejectedSyntax. The tree is
    returned unchecked; pass it to checker.check before evaluating it.
    """
    try:
        tree = ast.parse(source, filename=filename, mode="exec", feature_version=PYTHON_BASELINE)
    except SyntaxError as error:
        raise RejectedSyntax(
            error.msg, (filename, error.lineno, error.offset, error.text)
        ) from None
    except (RecursionError, MemoryError, ValueError) as error:
        raise RejectedSyntax(
            f"source cannot be parsed: {error}", (filename, None, None, None)
        ) from None
    _check_depth(tree, filename)
    return tree


def _check_depth(tree: ast.Module, filename: str) -> None:
    """Reject a tree deeper than MAX_TREE_DEPTH, walking it without recursion."""
    pending: list[tuple[ast.AST, int, ast.AST]] = [(tree, 1, tree)]
    while pending:
        node, depth, located = pending.pop()
        if hasattr(node, "lineno"):
            located = node
        if depth > MAX_TREE_DEPTH:
            raise RejectedSyntax.at(located, filename, f"nested more than {MAX_TREE_DEPTH} deep")
        pending.extend((child, depth + 1, located) for child in ast.iter_child_nodes(node))
