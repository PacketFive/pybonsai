# SPDX-License-Identifier: GPL-2.0
"""The PyBonsai value model (RFC 0001 sections 7.3 and 7.5).

Every value a file can hold is immutable:

========================  ========================================
PyBonsai source           Value during evaluation
========================  ========================================
``str``, ``int``, ...     The Python object itself
``(...)`` and ``[...]``   ``tuple``
``{k: v}``                FrozenMap
``{a, b}``                ``frozenset``, always iterated sorted
function or lambda        Function
prelude or host function  Builtin
host value                An instance of a type in host.Host.types
========================  ========================================
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .scope import Scope

if TYPE_CHECKING:
    from .host import Host


class FrozenMap(Mapping[object, object]):
    """A read-only, hashable mapping that keeps insertion order.

    ``keys``, ``values`` and ``items`` return tuples rather than views, as
    section 7.5 requires.
    """

    __slots__ = ("_data", "_hash")

    def __init__(
        self, items: Mapping[object, object] | tuple[tuple[object, object], ...] = ()
    ) -> None:
        """Copy ``items`` into a private dict. Later changes to the source have no effect."""
        raise NotImplementedError

    def __getitem__(self, key: object) -> object:
        raise NotImplementedError

    def __iter__(self) -> Iterator[object]:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __hash__(self) -> int:
        """Hash of the frozenset of items, computed once and cached."""
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError

    def get(self, key: object, default: object = None) -> object:
        raise NotImplementedError

    def keys(self) -> tuple[object, ...]:  # type: ignore[override]
        raise NotImplementedError

    def values(self) -> tuple[object, ...]:  # type: ignore[override]
        raise NotImplementedError

    def items(self) -> tuple[tuple[object, object], ...]:  # type: ignore[override]
        raise NotImplementedError


@dataclass(frozen=True, eq=False)
class Function:
    """A function defined in a PyBonsai file with ``def`` or ``lambda``.

    ``defaults`` and ``kw_defaults`` hold default values evaluated once,
    when the function is defined. ``closure`` is the scope the function was
    defined in. Equality is identity, so the evaluator can detect recursion
    by checking whether a Function is already on its call stack.
    """

    name: str
    params: ast.arguments
    defaults: tuple[object, ...]
    kw_defaults: FrozenMap
    body: tuple[ast.stmt, ...] | ast.expr
    closure: Scope
    node: ast.FunctionDef | ast.Lambda


@dataclass(frozen=True)
class Builtin:
    """A prelude function, host function or allow-listed method.

    ``impl`` is an ordinary Python callable. It receives PyBonsai values and
    its result is passed through freeze before the file sees it. When
    ``takes_limits`` is true the evaluator also passes ``limits=`` so the
    function can refuse a result before building it, as ``range`` does.
    """

    name: str
    impl: Callable[..., object]
    takes_limits: bool = False


def kind_of(value: object) -> str | None:
    """Return the allowlist.ATTRIBUTES key for ``value``.

    One of ``"str"``, ``"tuple"``, ``"mapping"`` or ``"frozenset"``, or None
    for every other value. Host values are handled by get_attribute.
    """
    raise NotImplementedError


def freeze(value: object, host: Host) -> object:
    """Convert a value built by Python code into a PyBonsai value.

    Lists become tuples, dicts become FrozenMaps and sets become frozensets,
    recursively. Instances of host types are returned unchanged. Any other
    type raises TypeError, so a host function cannot leak a mutable or
    unknown object into a file.
    """
    raise NotImplementedError


def iterate(value: object, node: ast.AST, filename: str) -> tuple[object, ...]:
    """Return the elements of an iterable PyBonsai value as a tuple.

    Tuples and strings in order, FrozenMap keys in insertion order and
    frozensets in sorted order. Any other value raises EvaluationError.
    """
    raise NotImplementedError


def get_attribute(value: object, name: str, host: Host, node: ast.AST, filename: str) -> object:
    """Read an allow-listed attribute of ``value``.

    For a language value, looks ``name`` up in ATTRIBUTES[kind_of(value)].
    For a host value, looks it up in host.attributes_of(value). Raises
    EvaluationError if it is not there. Methods are returned as Builtins
    bound to ``value``, so ``m.items()`` gives a tuple of pairs. Plain
    attribute values pass through freeze.
    """
    raise NotImplementedError
