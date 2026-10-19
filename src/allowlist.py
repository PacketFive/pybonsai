# SPDX-License-Identifier: GPL-2.0
"""The allow lists of RFC 0001 sections 7.3 to 7.5, as data.

This module holds no logic. The checker and the evaluator read these tables,
so a change to the language is a change here plus an RFC amendment.
"""

from __future__ import annotations

import ast

# Nodes that carry no behaviour of their own but appear in every tree:
# the module, name contexts and function parameters.
STRUCTURAL_NODES: frozenset[type[ast.AST]] = frozenset(
    {
        ast.Module,
        ast.Load,
        ast.Store,
        ast.arg,
    }
)

# Bitwise and shift operators and ``@`` are left out, because the RFC
# permits arithmetic, comparison and boolean logic only.
OPERATOR_NODES: frozenset[type[ast.AST]] = frozenset(
    {
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.UAdd,
        ast.USub,
        ast.Not,
        ast.And,
        ast.Or,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
    }
)

# Section 7.3, one line per row of the permitted constructs table.
CONSTRUCT_NODES: frozenset[type[ast.AST]] = frozenset(
    {
        ast.Constant,
        ast.JoinedStr,
        ast.FormattedValue,
        ast.Tuple,
        ast.List,
        ast.Dict,
        ast.Set,
        ast.Name,
        ast.Assign,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.IfExp,
        ast.Call,
        ast.keyword,
        ast.Starred,
        ast.Attribute,
        ast.Subscript,
        ast.Slice,
        ast.ListComp,
        ast.DictComp,
        ast.SetComp,
        ast.comprehension,
        ast.For,
        ast.FunctionDef,
        ast.Return,
        ast.Lambda,
        ast.arguments,
    }
)

PERMITTED_NODES: frozenset[type[ast.AST]] = STRUCTURAL_NODES | OPERATOR_NODES | CONSTRUCT_NODES

# Section 7.4. Used only to give a specific reason in error messages. Any
# node not in PERMITTED_NODES is rejected whether or not it appears here.
REJECTION_REASONS: dict[type[ast.AST], str] = {
    ast.While: "evaluation could fail to terminate",
    ast.Import: "imports bring in code outside the standard library",
    ast.ImportFrom: "imports bring in code outside the standard library",
    ast.AugAssign: "values are immutable",
    ast.AnnAssign: "values are immutable",
    ast.Delete: "values are immutable",
    ast.Global: "values are immutable",
    ast.Nonlocal: "values are immutable",
    ast.Try: "control flow that depends on failure",
    ast.TryStar: "control flow that depends on failure",
    ast.Raise: "control flow that depends on failure",
    ast.Assert: "control flow that depends on failure",
    ast.With: "resource handling implies I/O",
    ast.ClassDef: "classes create mutable objects",
    ast.GeneratorExp: "generators hold suspended state",
    ast.Yield: "generators hold suspended state",
    ast.YieldFrom: "generators hold suspended state",
    ast.AsyncFunctionDef: "async code holds suspended state",
    ast.AsyncFor: "async code holds suspended state",
    ast.AsyncWith: "async code holds suspended state",
    ast.Await: "async code holds suspended state",
    ast.TypeAlias: "type syntax has no meaning in a configuration",
    ast.TypeVar: "type syntax has no meaning in a configuration",
    ast.ParamSpec: "type syntax has no meaning in a configuration",
    ast.TypeVarTuple: "type syntax has no meaning in a configuration",
    ast.Match: "pattern matching binds names outside assignment",
    ast.NamedExpr: "assignment inside an expression",
}

# Literal types a Constant node may hold. bool is listed for clarity even
# though it is a subclass of int. bytes, complex and Ellipsis are rejected.
PERMITTED_CONSTANT_TYPES: tuple[type, ...] = (str, int, float, bool, type(None))

# Section 7.5 attribute allow list for the language's own types. Keys are
# the value kinds returned by values.kind_of(). Attributes of host types,
# such as Lattice's derivation, come from host.Host.types instead.
ATTRIBUTES: dict[str, frozenset[str]] = {
    "str": frozenset(
        {
            "lower",
            "upper",
            "strip",
            "lstrip",
            "rstrip",
            "split",
            "rsplit",
            "splitlines",
            "join",
            "replace",
            "startswith",
            "endswith",
            "removeprefix",
            "removesuffix",
            "partition",
            "rpartition",
            "count",
            "find",
            "isdigit",
            "isalpha",
            "isalnum",
        }
    ),
    "tuple": frozenset({"count", "index"}),
    "mapping": frozenset({"get", "keys", "values", "items"}),
    "frozenset": frozenset(
        {
            "union",
            "intersection",
            "difference",
            "issubset",
            "issuperset",
        }
    ),
}

# Every attribute name permitted on at least one language type. The checker
# adds the host's attribute names and rejects any other name before
# evaluation.
ALL_ATTRIBUTE_NAMES: frozenset[str] = frozenset().union(*ATTRIBUTES.values())
