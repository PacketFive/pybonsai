# SPDX-License-Identifier: GPL-2.0
"""Name scopes with single assignment (RFC 0001 section 7.3, Names).

A Scope maps names to values and points at its enclosing scope. The
outermost scope holds the host's names (host.Host.names). A name can be defined once per
scope; an inner scope may define a name that an outer scope also defines.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping


class Scope:
    """One level of name bindings."""

    def __init__(
        self, parent: Scope | None = None, names: Mapping[str, object] | None = None
    ) -> None:
        """Create a scope holding ``names``, looking up misses in ``parent``."""
        self.parent = parent
        self._names: dict[str, object] = dict(names or {})

    def child(self) -> Scope:
        """Return a new, empty scope whose parent is this one."""
        raise NotImplementedError

    def define(self, name: str, value: object, node: ast.AST, filename: str) -> None:
        """Bind ``name`` in this scope.

        Raises EvaluationError if the name is already bound in this scope.
        The checker rejects this case first; this check is a second line of
        defence.
        """
        raise NotImplementedError

    def lookup(self, name: str, node: ast.AST, filename: str) -> object:
        """Return the value of ``name`` from this scope or the nearest parent.

        Raises EvaluationError naming the unknown name. Python builtins are
        never consulted.
        """
        raise NotImplementedError

    def local_names(self) -> dict[str, object]:
        """Return a copy of the bindings made in this scope, in order."""
        raise NotImplementedError
