# SPDX-License-Identifier: GPL-2.0
"""The hermetic evaluator (RFC 0001 sections 7.2 to 7.7).

The evaluator interprets a tree that has already passed the checker. It
dispatches on node type: statements go to ``exec_<NodeType>`` and
expressions to ``eval_<NodeType>``. A node type with no method is an
internal error, because the checker should have rejected it.

Every evaluated node is charged to the Budget, and every computed value is
checked against the size limits.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Iterator

from .errors import EvaluationError
from .host import Host, default_host
from .limits import DEFAULT_LIMITS, Budget, LimitReached, Limits
from .prelude import pb_bool, pb_str
from .scope import Scope
from .values import Builtin, FrozenMap, Function, freeze, get_attribute, iterate, type_name

# Python errors that a wrong value in a file can cause. Each becomes an
# EvaluationError at the innermost node being evaluated.
_VALUE_ERRORS = (TypeError, ValueError, ZeroDivisionError, OverflowError, IndexError, KeyError)

_BINARY: dict[type, Callable[..., object]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_COMPARE: dict[type, Callable[..., object]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

_NUMBERS = (int, float, bool)
_OPERANDS = (int, float, bool, str, tuple)
_CONTAINERS = (str, tuple, FrozenMap, frozenset)
_TEXT = (str, int, float, bool, type(None))


class _Return(Exception):
    """Carries a ``return`` value out of nested statements to Evaluator.call.

    Internal only; it never escapes the evaluator.
    """

    def __init__(self, value: object) -> None:
        self.value = value


class Evaluator:
    """Evaluates one checked PyBonsai module."""

    def __init__(
        self,
        filename: str,
        host: Host | None = None,
        limits: Limits = DEFAULT_LIMITS,
    ) -> None:
        """Prepare an evaluation.

        ``host`` defaults to host.default_host(). Its ``names`` become the
        parent of the module scope.
        """
        self.filename = filename
        self.host = host if host is not None else default_host()
        self.limits = limits
        self.budget = Budget(limits, filename)
        self.call_stack: list[Function] = []

    # Entry point

    def evaluate_module(self, tree: ast.Module) -> FrozenMap:
        """Run every top-level statement and return the top-level names.

        A top-level ``return`` is an EvaluationError.
        """
        scope = Scope(Scope(names=self.host.names))  # type: ignore[arg-type]
        try:
            self.exec_block(tree.body, scope)
        except _Return:
            raise EvaluationError("return outside a function", self.filename) from None
        return FrozenMap(scope.local_names())  # type: ignore[arg-type]

    # Statements

    def exec_block(self, body: list[ast.stmt], scope: Scope) -> None:
        """Run statements in order. A Return raises _Return."""
        for statement in body:
            self.exec_stmt(statement, scope)

    def exec_stmt(self, node: ast.stmt, scope: Scope) -> None:
        """Charge the node and dispatch to ``exec_<NodeType>``."""
        self.budget.charge_node(node)
        self.budget.enter(node)
        method = getattr(self, f"exec_{type(node).__name__}", None)
        if method is None:
            raise self._error(node, f"internal error: {type(node).__name__} passed the checker")
        method(node, scope)
        self.budget.depth -= 1

    def exec_Assign(self, node: ast.Assign, scope: Scope) -> None:
        """Evaluate the value once and bind it to each target, unpacking tuples."""
        value = self.eval(node.value, scope)
        for target in node.targets:
            self._assign(target, value, scope)

    def exec_FunctionDef(self, node: ast.FunctionDef, scope: Scope) -> None:
        """Evaluate defaults now and bind a Function that closes over ``scope``."""
        scope.define(node.name, self._make_function(node.name, node, scope), node, self.filename)

    def exec_For(self, node: ast.For, scope: Scope) -> None:
        """Run the body once per element, each time in a fresh child scope.

        The iterable is evaluated first and in full, with values.iterate.
        """
        items = iterate(self.eval(node.iter, scope), node.iter, self.filename)
        for item in items:
            child = scope.child()
            self._assign(node.target, item, child)
            self.exec_block(node.body, child)

    def exec_Return(self, node: ast.Return, scope: Scope) -> None:
        """Evaluate the value, or None, and raise _Return."""
        raise _Return(None if node.value is None else self.eval(node.value, scope))

    # Expressions

    def eval(self, node: ast.expr, scope: Scope) -> object:
        """Charge the node, dispatch to ``eval_<NodeType>`` and check the result size."""
        budget = self.budget
        budget.charge_node(node)
        budget.enter(node)
        method = getattr(self, f"eval_{type(node).__name__}", None)
        if method is None:
            raise self._error(node, f"internal error: {type(node).__name__} passed the checker")
        try:
            value = method(node, scope)
        except _VALUE_ERRORS as error:
            raise self._error(node, _describe(error)) from None
        except LimitReached as error:
            raise budget.exceeded(error.limit, error.message, node) from None
        budget.depth -= 1
        return budget.check_value(value, node)

    def eval_Constant(self, node: ast.Constant, scope: Scope) -> object:
        """Return an int, float, str, bool or None literal; reject bytes and complex."""
        return node.value

    def eval_JoinedStr(self, node: ast.JoinedStr, scope: Scope) -> str:
        """Concatenate the parts of an f-string."""
        parts = [self.eval(value, scope) for value in node.values]
        size = sum(len(part) for part in parts)  # type: ignore[arg-type]
        if size > self.limits.max_str_len:
            raise self.budget.exceeded(
                "max_str_len", f"string longer than {self.limits.max_str_len}", node
            )
        return "".join(parts)  # type: ignore[arg-type]

    def eval_FormattedValue(self, node: ast.FormattedValue, scope: Scope) -> str:
        """Interpolate a string, number, bool, None or host value with prelude.pb_str.

        Any other value type is an EvaluationError.
        """
        value = self.eval(node.value, scope)
        if type(value) in _TEXT or self.host.attributes_of(value) is not None:
            return pb_str(value)
        raise self._error(node, f"a {type_name(value)} cannot be put in an f-string")

    def eval_Tuple(self, node: ast.Tuple, scope: Scope) -> tuple[object, ...]:
        """Evaluate elements in order, expanding Starred elements."""
        return self._elements(node.elts, scope)

    def eval_List(self, node: ast.List, scope: Scope) -> tuple[object, ...]:
        """Evaluate as a tuple, because lists are immutable in PyBonsai."""
        return self._elements(node.elts, scope)

    def eval_Set(self, node: ast.Set, scope: Scope) -> frozenset[object]:
        """Build a frozenset from the elements, expanding Starred elements."""
        return frozenset(self._elements(node.elts, scope))

    def eval_Dict(self, node: ast.Dict, scope: Scope) -> FrozenMap:
        """Build a FrozenMap. A repeated key is an EvaluationError, also through ``**``."""
        result: dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if key_node is None:
                mapping = self.eval(value_node, scope)
                if type(mapping) is not FrozenMap:
                    raise self._error(value_node, f"** needs a mapping, not {type_name(mapping)}")
                for key, value in mapping.items():
                    self._put(result, key, value, value_node)
            else:
                key = self.eval(key_node, scope)
                self._put(result, key, self.eval(value_node, scope), key_node)
        return FrozenMap(result)

    def eval_Name(self, node: ast.Name, scope: Scope) -> object:
        """Look the name up in ``scope``; an unknown name is an EvaluationError."""
        return scope.lookup(node.id, node, self.filename)

    def eval_BinOp(self, node: ast.BinOp, scope: Scope) -> object:
        """Apply an arithmetic or concatenation operator.

        Calls Budget.check_binop before computing. ``%`` with a string on
        the left is rejected, as is any operand that is not a number,
        string or tuple.
        """
        left = self.eval(node.left, scope)
        right = self.eval(node.right, scope)
        for operand in (left, right):
            if type(operand) not in _OPERANDS:
                raise self._error(node, f"a {type_name(operand)} cannot be used with an operator")
        if isinstance(node.op, ast.Mod) and type(left) is str:
            raise self._error(node, "% formatting is not permitted; use an f-string")
        self.budget.check_binop(node.op, left, right, node)
        result = _BINARY[type(node.op)](left, right)
        if type(result) is complex:
            raise self._error(node, "the result is a complex number")
        return result

    def eval_UnaryOp(self, node: ast.UnaryOp, scope: Scope) -> object:
        """Apply ``-``, ``+`` or ``not`` to a number or bool."""
        value = self.eval(node.operand, scope)
        if isinstance(node.op, ast.Not):
            return not pb_bool(value)
        if type(value) not in _NUMBERS:
            raise self._error(node, f"a {type_name(value)} cannot be negated")
        return -value if isinstance(node.op, ast.USub) else +value  # type: ignore[operator]

    def eval_BoolOp(self, node: ast.BoolOp, scope: Scope) -> object:
        """Short-circuit ``and`` and ``or`` as in Python."""
        is_and = isinstance(node.op, ast.And)
        value: object = None
        for operand in node.values:
            value = self.eval(operand, scope)
            if pb_bool(value) != is_and:
                return value
        return value

    def eval_Compare(self, node: ast.Compare, scope: Scope) -> bool:
        """Evaluate chained comparisons left to right, stopping at the first false one."""
        left = self.eval(node.left, scope)
        for op, right_node in zip(node.ops, node.comparators, strict=True):
            right = self.eval(right_node, scope)
            if isinstance(op, (ast.In, ast.NotIn)):
                if type(right) not in _CONTAINERS:
                    raise self._error(node, f"in needs a collection, not {type_name(right)}")
                result = (left in right) != isinstance(op, ast.NotIn)  # type: ignore[operator]
            else:
                result = pb_bool(_COMPARE[type(op)](left, right))
            if not result:
                return False
            left = right
        return True

    def eval_IfExp(self, node: ast.IfExp, scope: Scope) -> object:
        """Evaluate the test, then only the chosen branch."""
        branch = node.body if pb_bool(self.eval(node.test, scope)) else node.orelse
        return self.eval(branch, scope)

    def eval_Call(self, node: ast.Call, scope: Scope) -> object:
        """Evaluate the callee and arguments, expanding ``*`` and ``**``, then call."""
        callee = self.eval(node.func, scope)
        args = self._elements(node.args, scope)
        kwargs: dict[object, object] = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                mapping = self.eval(keyword.value, scope)
                if type(mapping) is not FrozenMap:
                    raise self._error(keyword, f"** needs a mapping, not {type_name(mapping)}")
                pairs = mapping.items()
            else:
                pairs = ((keyword.arg, self.eval(keyword.value, scope)),)
            for name, value in pairs:
                if type(name) is not str:
                    raise self._error(keyword, "keyword argument names must be strings")
                if name in kwargs:
                    raise self._error(keyword, f"keyword argument {name!r} given twice")
                kwargs[name] = value
        return self.call(callee, args, FrozenMap(kwargs), node)

    def eval_Attribute(self, node: ast.Attribute, scope: Scope) -> object:
        """Delegate to values.get_attribute with this evaluator's host."""
        value = self.eval(node.value, scope)
        return get_attribute(value, node.attr, self.host, node, self.filename)

    def eval_Subscript(self, node: ast.Subscript, scope: Scope) -> object:
        """Index or slice a tuple or string, or look up a key in a FrozenMap."""
        container = self.eval(node.value, scope)
        key = self.eval(node.slice, scope)
        kind = type(container)
        if kind is FrozenMap:
            assert isinstance(container, FrozenMap)  # noqa: S101
            if key not in container:
                raise self._error(node, f"key {key!r} is not in the mapping")
            return container[key]
        if kind is not tuple and kind is not str:
            raise self._error(node, f"a {type_name(container)} cannot be indexed")
        if type(key) is not int and type(key) is not slice:
            raise self._error(node, f"an index must be an int, not {type_name(key)}")
        return container[key]  # type: ignore[index]

    def eval_Slice(self, node: ast.Slice, scope: Scope) -> slice:
        """Build a slice from int or None bounds."""
        bounds = []
        for part in (node.lower, node.upper, node.step):
            value = None if part is None else self.eval(part, scope)
            if value is not None and type(value) is not int:
                raise self._error(node, f"a slice bound must be an int, not {type_name(value)}")
            bounds.append(value)
        return slice(*bounds)

    def eval_ListComp(self, node: ast.ListComp, scope: Scope) -> tuple[object, ...]:
        """Evaluate a list comprehension into a tuple."""
        return tuple(self._collect(node, scope, lambda inner: self.eval(node.elt, inner)))

    def eval_SetComp(self, node: ast.SetComp, scope: Scope) -> frozenset[object]:
        """Evaluate a set comprehension into a frozenset."""
        return frozenset(self._collect(node, scope, lambda inner: self.eval(node.elt, inner)))

    def eval_DictComp(self, node: ast.DictComp, scope: Scope) -> FrozenMap:
        """Build a FrozenMap; a repeated key is an EvaluationError, as for dict literals."""
        result: dict[object, object] = {}
        for inner in self._generate(node.generators, 0, scope):
            key = self.eval(node.key, inner)
            self._put(result, key, self.eval(node.value, inner), node.key)
            if len(result) > self.limits.max_collection_len:
                raise self._too_long(node)
        return FrozenMap(result)

    def eval_Lambda(self, node: ast.Lambda, scope: Scope) -> Function:
        """Create a Function capturing ``scope``."""
        return self._make_function("<lambda>", node, scope)

    # Calls and comprehensions

    def call(
        self, callee: object, args: tuple[object, ...], kwargs: FrozenMap, node: ast.AST
    ) -> object:
        """Call a Builtin or a Function.

        For a Function: reject recursion if a call to the same definition
        (the same ``node``) is already on call_stack, call
        Budget.enter_call, bind the arguments, run the body and return its
        value. The call stack, call depth and nesting depth are always
        restored, also on error. A Builtin is called directly, with
        ``limits=`` added when its ``takes_limits`` is set, and its result
        frozen. A TypeError or ValueError from a Builtin becomes an
        EvaluationError at ``node`` in Evaluator.eval. Any other callee is
        an EvaluationError.
        """
        if type(callee) is Builtin:
            assert isinstance(callee, Builtin)  # noqa: S101
            named = {str(key): value for key, value in kwargs.items()}
            if callee.takes_limits:
                if "limits" in named:
                    raise self._error(node, f"{callee.name}() takes no limits argument")
                named["limits"] = self.limits
            return freeze(callee.impl(*args, **named), self.host)
        if type(callee) is not Function:
            raise self._error(node, f"a {type_name(callee)} cannot be called")
        assert isinstance(callee, Function)  # noqa: S101
        if any(active.node is callee.node for active in self.call_stack):
            raise self._error(node, f"recursion into {callee.name}() is not permitted")
        budget = self.budget
        budget.enter_call(node)
        depth = budget.depth
        self.call_stack.append(callee)
        try:
            local = self.bind_arguments(callee, args, kwargs, node)
            if isinstance(callee.body, ast.expr):
                return self.eval(callee.body, local)
            self.exec_block(list(callee.body), local)
            return None
        except _Return as result:
            return result.value
        finally:
            self.call_stack.pop()
            budget.exit_call()
            budget.depth = depth

    def bind_arguments(
        self, fn: Function, args: tuple[object, ...], kwargs: FrozenMap, node: ast.AST
    ) -> Scope:
        """Return a child of ``fn.closure`` holding the parameters.

        Follows Python's rules for positional-only, positional, keyword-only
        and default parameters. ``*args`` and ``**kwargs`` parameters bind a
        tuple and a FrozenMap.
        """
        params = fn.params
        positional = [*params.posonlyargs, *params.args]
        positional_only = {arg.arg for arg in params.posonlyargs}
        keyword_names = {arg.arg for arg in (*params.args, *params.kwonlyargs)}
        bound: dict[str, object] = {}
        for arg, value in zip(positional, args, strict=False):
            bound[arg.arg] = value
        extra = args[len(positional) :]
        if extra and params.vararg is None:
            raise self._error(node, f"{fn.name}() takes {len(positional)} positional arguments")
        rest: dict[object, object] = {}
        for name, value in kwargs.items():
            if name in keyword_names:
                if name in bound:
                    raise self._error(node, f"{fn.name}() got two values for {name!r}")
                bound[name] = value  # type: ignore[index]
            elif params.kwarg is not None:
                rest[name] = value
            elif name in positional_only:
                raise self._error(node, f"{fn.name}() takes {name!r} by position only")
            else:
                raise self._error(node, f"{fn.name}() has no parameter {name!r}")
        first_default = len(positional) - len(fn.defaults)
        for index, arg in enumerate(positional):
            if arg.arg not in bound:
                if index < first_default:
                    raise self._error(node, f"{fn.name}() is missing argument {arg.arg!r}")
                bound[arg.arg] = fn.defaults[index - first_default]
        for arg in params.kwonlyargs:
            if arg.arg not in bound:
                if arg.arg not in fn.kw_defaults:
                    raise self._error(node, f"{fn.name}() is missing argument {arg.arg!r}")
                bound[arg.arg] = fn.kw_defaults[arg.arg]
        local = fn.closure.child()
        for arg in positional:
            local.define(arg.arg, bound[arg.arg], arg, self.filename)
        if params.vararg is not None:
            local.define(params.vararg.arg, tuple(extra), params.vararg, self.filename)
        for arg in params.kwonlyargs:
            local.define(arg.arg, bound[arg.arg], arg, self.filename)
        if params.kwarg is not None:
            local.define(params.kwarg.arg, FrozenMap(rest), params.kwarg, self.filename)
        return local

    def iterate_generators(
        self, generators: list[ast.comprehension], scope: Scope
    ) -> tuple[Scope, ...]:
        """Expand the ``for`` and ``if`` clauses of a comprehension.

        Returns one child scope per combination of loop values that passes
        every ``if``, in order. Each scope binds the targets of all clauses.
        """
        return tuple(self._generate(generators, 0, scope))

    # Helpers

    def _error(self, node: ast.AST, message: str) -> EvaluationError:
        """Return an EvaluationError at ``node``; the caller raises it."""
        return EvaluationError.at(node, self.filename, message)

    def _too_long(self, node: ast.AST) -> EvaluationError:
        """Return the LimitExceeded for a comprehension that grew too long."""
        return self.budget.exceeded(
            "max_collection_len", f"collection longer than {self.limits.max_collection_len}", node
        )

    def _make_function(
        self, name: str, node: ast.FunctionDef | ast.Lambda, scope: Scope
    ) -> Function:
        """Evaluate the defaults of ``node`` in ``scope`` and build a Function."""
        params = node.args
        defaults = tuple(self.eval(default, scope) for default in params.defaults)
        kw_defaults = FrozenMap(
            {
                arg.arg: self.eval(default, scope)
                for arg, default in zip(params.kwonlyargs, params.kw_defaults, strict=True)
                if default is not None
            }
        )
        body = node.body if isinstance(node, ast.Lambda) else tuple(node.body)
        return Function(name, params, defaults, kw_defaults, body, scope, node)

    def _elements(self, nodes: list[ast.expr], scope: Scope) -> tuple[object, ...]:
        """Evaluate expressions in order, expanding ``*`` elements in place."""
        result: list[object] = []
        for element in nodes:
            if isinstance(element, ast.Starred):
                result.extend(iterate(self.eval(element.value, scope), element, self.filename))
            else:
                result.append(self.eval(element, scope))
            if len(result) > self.limits.max_collection_len:
                raise self._too_long(element)
        return tuple(result)

    def _put(self, result: dict[object, object], key: object, value: object, node: ast.AST) -> None:
        """Add a key to a mapping under construction, rejecting a repeated key."""
        if key in result:
            raise self._error(node, f"key {key!r} appears more than once")
        result[key] = value

    def _assign(self, target: ast.expr, value: object, scope: Scope) -> None:
        """Bind ``value`` to a name, or unpack it into a tuple of targets."""
        if isinstance(target, ast.Name):
            scope.define(target.id, value, target, self.filename)
            return
        assert isinstance(target, ast.Tuple)  # noqa: S101
        items = iterate(value, target, self.filename)
        if len(items) != len(target.elts):
            raise self._error(
                target, f"cannot unpack {len(items)} values into {len(target.elts)} names"
            )
        for element, item in zip(target.elts, items, strict=True):
            self._assign(element, item, scope)

    def _collect(
        self,
        node: ast.ListComp | ast.SetComp,
        scope: Scope,
        element: Callable[[Scope], object],
    ) -> list[object]:
        """Evaluate a comprehension element once per generated scope."""
        result: list[object] = []
        for inner in self._generate(node.generators, 0, scope):
            result.append(element(inner))
            if len(result) > self.limits.max_collection_len:
                raise self._too_long(node)
        return result

    def _generate(
        self, generators: list[ast.comprehension], index: int, scope: Scope
    ) -> Iterator[Scope]:
        """Yield the scopes of iterate_generators one at a time."""
        if index == len(generators):
            yield scope
            return
        generator = generators[index]
        items = iterate(self.eval(generator.iter, scope), generator.iter, self.filename)
        for item in items:
            inner = scope.child()
            self._assign(generator.target, item, inner)
            if all(pb_bool(self.eval(test, inner)) for test in generator.ifs):
                yield from self._generate(generators, index + 1, inner)


def _describe(error: Exception) -> str:
    """Turn a Python error into a message for a file author."""
    if isinstance(error, KeyError):
        return f"key {error.args[0]!r} is not present" if error.args else "key not present"
    if isinstance(error, ZeroDivisionError):
        return "division by zero"
    return str(error) or type(error).__name__
