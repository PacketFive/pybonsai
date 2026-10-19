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

from .host import Host, default_host
from .limits import DEFAULT_LIMITS, Budget, Limits
from .scope import Scope
from .values import FrozenMap, Function


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
        self.budget = Budget(limits, filename)
        self.call_stack: list[Function] = []

    # Entry point

    def evaluate_module(self, tree: ast.Module) -> FrozenMap:
        """Run every top-level statement and return the top-level names.

        A top-level ``return`` is an EvaluationError.
        """
        raise NotImplementedError

    # Statements

    def exec_block(self, body: list[ast.stmt], scope: Scope) -> None:
        """Run statements in order. A Return raises _Return."""
        raise NotImplementedError

    def exec_stmt(self, node: ast.stmt, scope: Scope) -> None:
        """Charge the node and dispatch to ``exec_<NodeType>``."""
        raise NotImplementedError

    def exec_Assign(self, node: ast.Assign, scope: Scope) -> None:
        """Evaluate the value once and bind it to each target, unpacking tuples."""
        raise NotImplementedError

    def exec_FunctionDef(self, node: ast.FunctionDef, scope: Scope) -> None:
        """Evaluate defaults now and bind a Function that closes over ``scope``."""
        raise NotImplementedError

    def exec_For(self, node: ast.For, scope: Scope) -> None:
        """Run the body once per element, each time in a fresh child scope.

        The iterable is evaluated first and in full, with values.iterate.
        """
        raise NotImplementedError

    def exec_Return(self, node: ast.Return, scope: Scope) -> None:
        """Evaluate the value, or None, and raise _Return."""
        raise NotImplementedError

    # Expressions

    def eval(self, node: ast.expr, scope: Scope) -> object:
        """Charge the node, dispatch to ``eval_<NodeType>`` and check the result size."""
        raise NotImplementedError

    def eval_Constant(self, node: ast.Constant, scope: Scope) -> object:
        raise NotImplementedError

    def eval_JoinedStr(self, node: ast.JoinedStr, scope: Scope) -> str:
        """Concatenate the parts of an f-string."""
        raise NotImplementedError

    def eval_FormattedValue(self, node: ast.FormattedValue, scope: Scope) -> str:
        """Interpolate a string, number, bool, None or host value with prelude.pb_str.

        Any other value type is an EvaluationError.
        """
        raise NotImplementedError

    def eval_Tuple(self, node: ast.Tuple, scope: Scope) -> tuple[object, ...]:
        """Evaluate elements in order, expanding Starred elements."""
        raise NotImplementedError

    def eval_List(self, node: ast.List, scope: Scope) -> tuple[object, ...]:
        """Same as a tuple, because lists are immutable in PyBonsai."""
        raise NotImplementedError

    def eval_Set(self, node: ast.Set, scope: Scope) -> frozenset[object]:
        raise NotImplementedError

    def eval_Dict(self, node: ast.Dict, scope: Scope) -> FrozenMap:
        """Build a FrozenMap. A repeated key is an EvaluationError, also through ``**``."""
        raise NotImplementedError

    def eval_Name(self, node: ast.Name, scope: Scope) -> object:
        raise NotImplementedError

    def eval_BinOp(self, node: ast.BinOp, scope: Scope) -> object:
        """Apply an arithmetic or concatenation operator.

        Calls Budget.check_binop before computing. ``%`` with a string on
        the left is rejected, as is any operand that is not a number,
        string or tuple.
        """
        raise NotImplementedError

    def eval_UnaryOp(self, node: ast.UnaryOp, scope: Scope) -> object:
        raise NotImplementedError

    def eval_BoolOp(self, node: ast.BoolOp, scope: Scope) -> object:
        """Short-circuit ``and`` and ``or`` as in Python."""
        raise NotImplementedError

    def eval_Compare(self, node: ast.Compare, scope: Scope) -> bool:
        """Evaluate chained comparisons left to right, stopping at the first false one."""
        raise NotImplementedError

    def eval_IfExp(self, node: ast.IfExp, scope: Scope) -> object:
        raise NotImplementedError

    def eval_Call(self, node: ast.Call, scope: Scope) -> object:
        """Evaluate the callee and arguments, expanding ``*`` and ``**``, then call."""
        raise NotImplementedError

    def eval_Attribute(self, node: ast.Attribute, scope: Scope) -> object:
        """Delegate to values.get_attribute with this evaluator's host."""
        raise NotImplementedError

    def eval_Subscript(self, node: ast.Subscript, scope: Scope) -> object:
        """Index or slice a tuple or string, or look up a key in a FrozenMap."""
        raise NotImplementedError

    def eval_Slice(self, node: ast.Slice, scope: Scope) -> slice:
        """Build a slice from int or None bounds."""
        raise NotImplementedError

    def eval_ListComp(self, node: ast.ListComp, scope: Scope) -> tuple[object, ...]:
        raise NotImplementedError

    def eval_SetComp(self, node: ast.SetComp, scope: Scope) -> frozenset[object]:
        raise NotImplementedError

    def eval_DictComp(self, node: ast.DictComp, scope: Scope) -> FrozenMap:
        """A repeated key is an EvaluationError, as for dict literals."""
        raise NotImplementedError

    def eval_Lambda(self, node: ast.Lambda, scope: Scope) -> Function:
        raise NotImplementedError

    # Calls and comprehensions

    def call(
        self, callee: object, args: tuple[object, ...], kwargs: FrozenMap, node: ast.AST
    ) -> object:
        """Call a Builtin or a Function.

        For a Function: reject recursion if it is already on call_stack,
        call Budget.enter_call, bind the arguments, run the body and return
        its value. The call stack and budget are always restored, also on
        error. A Builtin is called directly, with ``limits=`` added when
        its ``takes_limits`` is set, and its result frozen. A TypeError or
        ValueError from a Builtin becomes an EvaluationError at ``node``.
        Any other callee is an EvaluationError.
        """
        raise NotImplementedError

    def bind_arguments(
        self, fn: Function, args: tuple[object, ...], kwargs: FrozenMap, node: ast.AST
    ) -> Scope:
        """Return a child of ``fn.closure`` holding the parameters.

        Follows Python's rules for positional-only, positional, keyword-only
        and default parameters. ``*args`` and ``**kwargs`` parameters bind a
        tuple and a FrozenMap.
        """
        raise NotImplementedError

    def iterate_generators(
        self, generators: list[ast.comprehension], scope: Scope
    ) -> tuple[Scope, ...]:
        """Expand the ``for`` and ``if`` clauses of a comprehension.

        Returns one child scope per combination of loop values that passes
        every ``if``, in order. Each scope binds the targets of all clauses.
        """
        raise NotImplementedError
