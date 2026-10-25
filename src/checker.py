# SPDX-License-Identifier: GPL-2.0
"""Static check of a syntax tree before evaluation (RFC 0001 sections 7.2 to 7.5).

The checker visits every node once and raises RejectedSyntax at the first
violation. It enforces every rule that can be decided from the tree alone:

* the node type is in allowlist.PERMITTED_NODES;
* constants are of a permitted type;
* f-strings use no format spec and no ``!s``, ``!r`` or ``!a`` conversion;
* attribute names are in allowlist.ALL_ATTRIBUTE_NAMES or the host's
  attribute names, and never start with ``_``;
* functions have no decorators and no type parameters;
* assignment targets are plain names or tuples of plain names;
* a name is assigned at most once per scope;
* a dictionary literal does not repeat a constant key.

Rules that depend on values, such as ``%`` on a string or an attribute used
on the wrong type, are left to the evaluator.
"""

from __future__ import annotations

import ast

from .allowlist import ALL_ATTRIBUTE_NAMES
from .errors import RejectedSyntax


class Checker(ast.NodeVisitor):
    """Walks a tree and rejects anything outside the allow list.

    Keeps a stack of scopes, one set of assigned names per module, function,
    lambda, comprehension and ``for`` body, to enforce single assignment.
    """

    def __init__(self, filename: str, host_attributes: frozenset[str] = frozenset()) -> None:
        """``host_attributes`` is host.Host.attribute_names() for the embedding program."""
        self.filename = filename
        self.attribute_names = ALL_ATTRIBUTE_NAMES | host_attributes
        self.scopes: list[set[str]] = []

    def check(self, tree: ast.Module) -> None:
        """Check the whole module. Returns None or raises RejectedSyntax."""
        raise NotImplementedError

    def generic_visit(self, node: ast.AST) -> None:
        """Reject node types outside PERMITTED_NODES, then visit children.

        Uses REJECTION_REASONS for the message when the node type is listed
        there, and a generic reason otherwise.
        """
        raise NotImplementedError

    def visit_Constant(self, node: ast.Constant) -> None:
        """Reject bytes, complex and Ellipsis literals."""
        raise NotImplementedError

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        """Reject a format spec or any conversion."""
        raise NotImplementedError

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Reject attribute names that start with ``_`` or are not in ``self.attribute_names``."""
        raise NotImplementedError

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check targets are names or tuples of names, and record each name.

        Chained assignment ``a = b = 1`` is permitted as long as every name
        is new in the current scope.
        """
        raise NotImplementedError

    def visit_Dict(self, node: ast.Dict) -> None:
        """Reject a literal whose constant keys repeat.

        Keys that are not constants are checked again by the evaluator once
        their values are known. A ``None`` key marks ``**`` unpacking.
        """
        raise NotImplementedError

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Reject decorators and type parameters, then check the body in a new scope.

        The function name is recorded in the enclosing scope and the
        parameter names in the new scope.
        """
        raise NotImplementedError

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Check the body of a lambda in a new scope holding its parameters."""
        raise NotImplementedError

    def visit_For(self, node: ast.For) -> None:
        """Check a loop. The target and body names live in a per-iteration scope.

        ``orelse`` must be empty, because ``for ... else`` only makes sense
        with ``break``, which is not permitted.
        """
        raise NotImplementedError

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Check a list comprehension in its own scope."""
        raise NotImplementedError

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Check a set comprehension in its own scope."""
        raise NotImplementedError

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Check a dict comprehension in its own scope."""
        raise NotImplementedError

    def _visit_comprehension_scope(self, node: ast.ListComp | ast.SetComp | ast.DictComp) -> None:
        """Shared logic for the three comprehensions.

        Rejects ``async`` comprehensions and binds each generator's target
        names in the comprehension scope.
        """
        raise NotImplementedError

    def _bind(self, target: ast.expr) -> None:
        """Record the names in ``target`` in the current scope.

        Raises RejectedSyntax if the target is not a Name or a Tuple of
        Names, or if a name is already bound in the current scope.
        """
        raise NotImplementedError

    def _reject(self, node: ast.AST, reason: str) -> RejectedSyntax:
        """Return a RejectedSyntax for ``node``; the caller raises it."""
        raise NotImplementedError


def check(tree: ast.Module, filename: str, host_attributes: frozenset[str] = frozenset()) -> None:
    """Run ``Checker(filename, host_attributes).check(tree)``."""
    raise NotImplementedError
