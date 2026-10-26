# SPDX-License-Identifier: GPL-2.0
"""Static check of a syntax tree before evaluation (RFC 0001 sections 7.2 to 7.5).

The checker visits every node once and raises RejectedSyntax at the first
violation. It enforces every rule that can be decided from the tree alone:

* the node type is in allowlist.PERMITTED_NODES;
* constants are of a permitted type;
* f-strings use no format spec and no ``!s``, ``!r`` or ``!a`` conversion;
* attribute names are in allowlist.ALL_ATTRIBUTE_NAMES or the host's
  attribute names, and never start with ``_``;
* functions have no decorators, type parameters or annotations;
* ``return`` appears only inside a function, and ``for`` has no ``else``;
* ``is`` and ``is not`` compare with the constant None, True or False only;
* assignment targets are plain names or tuples of them, nested or not;
* a name is assigned at most once per scope;
* a dictionary literal does not repeat a constant key.

Rules that depend on values, such as ``%`` on a string or an attribute used
on the wrong type, are left to the evaluator.
"""

from __future__ import annotations

import ast

from .allowlist import (
    ALL_ATTRIBUTE_NAMES,
    PERMITTED_CONSTANT_TYPES,
    PERMITTED_NODES,
    REJECTION_REASONS,
)
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
        self.function_depth = 0

    def check(self, tree: ast.Module) -> None:
        """Check the whole module. Returns None or raises RejectedSyntax."""
        self.scopes = [set()]
        self.function_depth = 0
        self.visit(tree)

    def generic_visit(self, node: ast.AST) -> None:
        """Reject node types outside PERMITTED_NODES, then visit children.

        Uses REJECTION_REASONS for the message when the node type is listed
        there, and a generic reason otherwise.
        """
        if type(node) not in PERMITTED_NODES:
            reason = REJECTION_REASONS.get(type(node), "it is outside the PyBonsai allow list")
            raise self._reject(node, reason)
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Reject bytes, complex and Ellipsis literals."""
        if type(node.value) not in PERMITTED_CONSTANT_TYPES:
            raise self._reject(node, f"{type(node.value).__name__} literals are not permitted")

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        """Reject a format spec or any conversion."""
        if node.conversion != -1:
            raise self._reject(node, "f-string conversions are not permitted")
        if node.format_spec is not None:
            raise self._reject(node, "f-string format specs are not permitted")
        self.visit(node.value)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Reject attribute names that start with ``_`` or are not in ``self.attribute_names``."""
        if node.attr.startswith("_") or node.attr not in self.attribute_names:
            raise self._reject(node, f"attribute {node.attr!r} is not on the allow list")
        self.visit(node.value)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check targets are names or tuples of names, and record each name.

        Chained assignment ``a = b = 1`` is permitted as long as every name
        is new in the current scope.
        """
        self.visit(node.value)
        for target in node.targets:
            self._bind(target)

    def visit_Dict(self, node: ast.Dict) -> None:
        """Reject a literal whose constant keys repeat.

        Keys that are not constants are checked again by the evaluator once
        their values are known. A ``None`` key marks ``**`` unpacking.
        """
        seen: set[object] = set()
        for key in node.keys:
            if isinstance(key, ast.Constant):
                if key.value in seen:
                    raise self._reject(node, f"key {key.value!r} appears more than once")
                seen.add(key.value)
        self._visit_children(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Reject decorators and type parameters, then check the body in a new scope.

        The function name is recorded in the enclosing scope and the
        parameter names in the new scope.
        """
        if node.decorator_list:
            raise self._reject(node, "decorators are not permitted")
        if node.type_params:
            raise self._reject(node, "type parameters are not permitted")
        if node.returns is not None:
            raise self._reject(node, "annotations are not permitted")
        self._visit_defaults(node.args)
        self._bind_name(node.name, node)
        self.scopes.append(set())
        self.function_depth += 1
        self._bind_parameters(node.args)
        for statement in node.body:
            self.visit(statement)
        self.function_depth -= 1
        self.scopes.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Check the body of a lambda in a new scope holding its parameters."""
        self._visit_defaults(node.args)
        self.scopes.append(set())
        self._bind_parameters(node.args)
        self.visit(node.body)
        self.scopes.pop()

    def visit_For(self, node: ast.For) -> None:
        """Check a loop. The target and body names live in a per-iteration scope.

        ``orelse`` must be empty, because ``for ... else`` only makes sense
        with ``break``, which is not permitted.
        """
        if node.orelse:
            raise self._reject(node, "for ... else needs break, which is not permitted")
        self.visit(node.iter)
        self.scopes.append(set())
        self._bind(node.target)
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Check a list comprehension in its own scope."""
        self._visit_comprehension_scope(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Check a set comprehension in its own scope."""
        self._visit_comprehension_scope(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Check a dict comprehension in its own scope."""
        self._visit_comprehension_scope(node)

    def _visit_comprehension_scope(self, node: ast.ListComp | ast.SetComp | ast.DictComp) -> None:
        """Shared logic for the three comprehensions.

        Rejects ``async`` comprehensions and binds each generator's target
        names in the comprehension scope.
        """
        self.scopes.append(set())
        for generator in node.generators:
            if generator.is_async:
                raise self._reject(generator, "async comprehensions are not permitted")
            self.visit(generator.iter)
            self._bind(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.scopes.pop()

    def _bind(self, target: ast.expr) -> None:
        """Record the names in ``target`` in the current scope.

        Raises RejectedSyntax if the target is not a Name or a Tuple of
        targets, or if a name is already bound in the current scope.
        """
        if isinstance(target, ast.Name):
            self._bind_name(target.id, target)
        elif isinstance(target, ast.Tuple):
            for element in target.elts:
                self._bind(element)
        else:
            raise self._reject(target, "only names and tuples of names can be assigned")

    def visit_Return(self, node: ast.Return) -> None:
        """Reject ``return`` outside a function body."""
        if self.function_depth == 0:
            raise self._reject(node, "return outside a function")
        self._visit_children(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        """Permit ``is`` and ``is not`` only against the constant None, True or False.

        Identity of other values depends on how the interpreter shares
        objects, so the result could differ between runs.
        """
        operands = [node.left, *node.comparators]
        for index, op in enumerate(node.ops):
            if isinstance(op, (ast.Is, ast.IsNot)) and not (
                _is_singleton(operands[index]) or _is_singleton(operands[index + 1])
            ):
                raise self._reject(node, "is compares only with None, True or False")
        self._visit_children(node)

    def _visit_defaults(self, args: ast.arguments) -> None:
        """Check default values, which are evaluated in the enclosing scope."""
        for default in args.defaults:
            self.visit(default)
        for default in args.kw_defaults:
            if default is not None:
                self.visit(default)

    def _bind_parameters(self, args: ast.arguments) -> None:
        """Record every parameter name in the current scope and reject annotations."""
        parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        parameters += [arg for arg in (args.vararg, args.kwarg) if arg is not None]
        for arg in parameters:
            if arg.annotation is not None:
                raise self._reject(arg, "annotations are not permitted")
            self._bind_name(arg.arg, arg)

    def _bind_name(self, name: str, node: ast.AST) -> None:
        """Record ``name`` in the current scope, rejecting a second assignment."""
        scope = self.scopes[-1]
        if name in scope:
            raise self._reject(node, f"name {name!r} is already assigned in this scope")
        scope.add(name)

    def _visit_children(self, node: ast.AST) -> None:
        """Visit every child node, with one Python frame per tree level."""
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    def _reject(self, node: ast.AST, reason: str) -> RejectedSyntax:
        """Return a RejectedSyntax for ``node``; the caller raises it."""
        return RejectedSyntax.at(node, self.filename, reason)


def check(tree: ast.Module, filename: str, host_attributes: frozenset[str] = frozenset()) -> None:
    """Run ``Checker(filename, host_attributes).check(tree)``."""
    Checker(filename, host_attributes).check(tree)


def _is_singleton(node: ast.expr) -> bool:
    """Return True for the constants None, True and False."""
    return isinstance(node, ast.Constant) and (node.value is None or type(node.value) is bool)
