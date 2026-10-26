# SPDX-License-Identifier: GPL-2.0
"""The PyBonsai value model (RFC 0001 sections 7.3 and 7.5).

Every value a file can hold is immutable:

========================  ========================================
PyBonsai source           Value during evaluation
========================  ========================================
``str``, ``int``, ...     The Python object itself
``(...)`` and ``[...]``   ``tuple``
``{k: v}``                FrozenMap
``{a, b}``                ``frozenset``, iterated in canonical order
function or lambda        Function
prelude or host function  Builtin
host value                An instance of a type in host.Host.types
========================  ========================================
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .allowlist import ATTRIBUTES
from .errors import EvaluationError
from .limits import LimitReached, Limits
from .scope import Scope

if TYPE_CHECKING:
    from .host import Host


class FrozenMap(Mapping[object, object]):
    """A read-only, hashable mapping that keeps insertion order.

    ``keys``, ``values`` and ``items`` return tuples rather than views, as
    section 7.5 requires. A FrozenMap is equal only to another FrozenMap
    with the same items, in any order, and never to a plain dict.
    """

    __slots__ = ("_data", "_hash")

    _data: dict[object, object]
    _hash: int | None

    def __init__(
        self, items: Mapping[Any, object] | tuple[tuple[object, object], ...] = ()
    ) -> None:
        """Copy ``items`` into a private dict. Later changes to the source have no effect."""
        object.__setattr__(self, "_data", dict(items))
        object.__setattr__(self, "_hash", None)

    def __setattr__(self, name: str, value: object) -> None:
        """Refuse every attribute assignment."""
        raise AttributeError("FrozenMap is read-only")

    def __delattr__(self, name: str) -> None:
        """Refuse every attribute deletion."""
        raise AttributeError("FrozenMap is read-only")

    def __getitem__(self, key: object) -> object:
        """Return the value for ``key``; a missing key raises KeyError."""
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        """Return True if ``key`` is present."""
        return key in self._data

    def __iter__(self) -> Iterator[object]:
        """Iterate over keys in insertion order."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of keys."""
        return len(self._data)

    def __hash__(self) -> int:
        """Hash of the frozenset of items, computed once and cached."""
        if self._hash is None:
            object.__setattr__(self, "_hash", hash(frozenset(self._data.items())))
        assert self._hash is not None  # noqa: S101
        return self._hash

    def __eq__(self, other: object) -> bool:
        """Compare equal to another FrozenMap with the same items, in any order."""
        if not isinstance(other, FrozenMap):
            return NotImplemented
        return self._data == other._data

    def __ne__(self, other: object) -> bool:
        """Return the negation of ``__eq__``."""
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __repr__(self) -> str:
        """Return ``FrozenMap({...})`` for debugging output."""
        return f"FrozenMap({self._data!r})"

    def __reduce__(self) -> tuple[type[FrozenMap], tuple[tuple[tuple[object, object], ...]]]:
        """Support copy and pickle by rebuilding from the items."""
        return (FrozenMap, (self.items(),))

    def get(self, key: object, default: object = None) -> object:
        """Return the value for ``key``, or ``default`` if it is missing."""
        return self._data.get(key, default)

    def keys(self) -> tuple[object, ...]:  # type: ignore[override]
        """Return the keys as a tuple in insertion order."""
        return tuple(self._data)

    def values(self) -> tuple[object, ...]:  # type: ignore[override]
        """Return the values as a tuple in insertion order."""
        return tuple(self._data.values())

    def items(self) -> tuple[tuple[object, object], ...]:  # type: ignore[override]
        """Return ``(key, value)`` pairs as a tuple in insertion order."""
        return tuple(self._data.items())


@dataclass(frozen=True, eq=False)
class Function:
    """A function defined in a PyBonsai file with ``def`` or ``lambda``.

    ``defaults`` and ``kw_defaults`` hold default values evaluated once,
    when the function is defined. ``closure`` is the scope the function was
    defined in. Equality is identity. The evaluator detects recursion by
    ``node``: a function whose definition is already being called is
    rejected, even when it is a new Function object made by a later call,
    so the number of definitions in a file bounds the call depth.
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


_KINDS: dict[type, str] = {
    str: "str",
    tuple: "tuple",
    FrozenMap: "mapping",
    frozenset: "frozenset",
}

_SCALARS: frozenset[type] = frozenset({str, int, float, bool, type(None)})


def kind_of(value: object) -> str | None:
    """Return the allowlist.ATTRIBUTES key for ``value``.

    One of ``"str"``, ``"tuple"``, ``"mapping"`` or ``"frozenset"``, or None
    for every other value. The type must match exactly, so a subclass such
    as a named tuple is not mistaken for a language value. Host values are
    handled by get_attribute.
    """
    return _KINDS.get(type(value))


def freeze(value: object, host: Host) -> object:
    """Convert a value built by Python code into a PyBonsai value.

    Lists become tuples, dicts become FrozenMaps and sets become frozensets,
    recursively. Instances of host types are returned unchanged. Any other
    type raises TypeError, so a host function cannot leak a mutable or
    unknown object into a file. A value that contains itself raises
    ValueError.
    """
    return _freeze(value, host, set())


def _freeze(value: object, host: Host, active: set[int]) -> object:
    kind = type(value)
    if kind in _SCALARS or kind is Function or kind is Builtin or kind in host.types:
        return value
    if kind in (tuple, list, dict, FrozenMap, set, frozenset):
        ident = id(value)
        if ident in active:
            raise ValueError("a value cannot contain itself")
        active.add(ident)
        try:
            if isinstance(value, (tuple, list)):
                return tuple(_freeze(item, host, active) for item in value)
            if isinstance(value, (dict, FrozenMap)):
                pairs = value.items()
                return FrozenMap(
                    tuple((_freeze(k, host, active), _freeze(v, host, active)) for k, v in pairs)
                )
            assert isinstance(value, (set, frozenset))  # noqa: S101
            return frozenset(_freeze(item, host, active) for item in value)
        finally:
            active.discard(ident)
    raise TypeError(f"a value of type {kind.__name__} cannot be used in PyBonsai")


def ordered(value: object) -> tuple[object, ...]:
    """Return the elements of a collection in their defined order.

    Tuples and strings in order, FrozenMap keys in insertion order and
    frozensets in canonical order (see canonical_key), because their native
    order changes between runs. Raises TypeError for any other value, or
    for a frozenset holding a value that has no canonical order. Every
    iteration in PyBonsai goes through this function.
    """
    kind = type(value)
    if kind is tuple:
        return value  # type: ignore[return-value]
    if kind is str or kind is FrozenMap:
        return tuple(value)  # type: ignore[arg-type]
    if kind is frozenset:
        return tuple(sorted(value, key=canonical_key))  # type: ignore[arg-type]
    raise TypeError(f"a value of type {_type_name(value)} cannot be iterated")


_NUMBER_TYPES = (bool, int, float)


def canonical_key(value: object) -> tuple[object, ...]:
    """Return a sort key that puts any two set elements in a fixed order.

    Python's own ``<`` is only a partial order on sets and NaN, and fails
    between types, so sorting with it could depend on the hash seed. This
    key orders by kind first (None, numbers, strings, tuples, frozensets,
    mappings, host values with ``__str__``), then by value. Mappings and
    frozensets are compared by their sorted contents. A Function, a Builtin
    or a host value without ``__str__`` raises TypeError.
    """
    kind = type(value)
    if value is None:
        return (0,)
    if kind in _NUMBER_TYPES:
        number = value
        assert isinstance(number, (int, float))  # noqa: S101
        return (1, 1) if number != number else (1, 0, number)
    if kind is str:
        return (2, value)
    if kind is tuple:
        assert isinstance(value, tuple)  # noqa: S101
        return (3, tuple(canonical_key(item) for item in value))
    if kind is frozenset:
        assert isinstance(value, frozenset)  # noqa: S101
        return (4, tuple(sorted(canonical_key(item) for item in value)))
    if kind is FrozenMap:
        assert isinstance(value, FrozenMap)  # noqa: S101
        pairs = ((canonical_key(k), canonical_key(v)) for k, v in value.items())
        return (5, tuple(sorted(pairs)))
    if kind not in (Function, Builtin) and kind.__str__ is not object.__str__:
        return (6, f"{kind.__module__}.{kind.__qualname__}", str(value))
    raise TypeError(f"a {_type_name(value)} in a set has no defined order")


def iterate(value: object, node: ast.AST, filename: str) -> tuple[object, ...]:
    """Return the elements of an iterable PyBonsai value as a tuple.

    Tuples and strings in order, FrozenMap keys in insertion order and
    frozensets in canonical order. Any other value raises EvaluationError.
    """
    try:
        return ordered(value)
    except TypeError as error:
        raise EvaluationError.at(node, filename, str(error)) from None


def type_name(value: object) -> str:
    """Return the PyBonsai name of a value's type, for error messages."""
    return _type_name(value)


def _type_name(value: object) -> str:
    kind = kind_of(value)
    if kind is not None:
        return kind
    if isinstance(value, (Function, Builtin)):
        return "function"
    if value is None:
        return "None"
    return type(value).__name__


def _method(value: object, kind: str, name: str) -> Builtin:
    """Return an allow-listed method of a language value as a Builtin."""
    if kind == "str" and name == "join":
        sep = value
        assert isinstance(sep, str)  # noqa: S101

        def join(items: object, *, limits: Limits) -> str:
            parts = ordered(items)
            if not all(type(part) is str for part in parts):
                raise TypeError("str.join needs a collection of strings")
            size = sum(len(part) for part in parts) + len(sep) * max(len(parts) - 1, 0)  # type: ignore[arg-type]
            if size > limits.max_str_len:
                raise LimitReached("max_str_len", f"string longer than {limits.max_str_len}")
            return sep.join(parts)  # type: ignore[arg-type]

        return Builtin("str.join", join, takes_limits=True)
    if kind == "str" and name == "replace":
        text = value
        assert isinstance(text, str)  # noqa: S101

        def replace(old: str, new: str, count: int = -1, *, limits: Limits) -> str:
            if type(old) is not str or type(new) is not str:
                raise TypeError("str.replace needs strings")
            found = len(text) + 1 if old == "" else text.count(old)
            if count >= 0:
                found = min(found, count)
            if len(text) + found * (len(new) - len(old)) > limits.max_str_len:
                raise LimitReached("max_str_len", f"string longer than {limits.max_str_len}")
            return text.replace(old, new, count)

        return Builtin("str.replace", replace, takes_limits=True)
    if kind == "frozenset":
        target = value
        assert isinstance(target, frozenset)  # noqa: S101
        method = getattr(target, name)

        def set_method(*others: object) -> object:
            return method(*(frozenset(ordered(other)) for other in others))

        return Builtin(f"frozenset.{name}", set_method)
    return Builtin(f"{kind}.{name}", getattr(value, name))


def get_attribute(value: object, name: str, host: Host, node: ast.AST, filename: str) -> object:
    """Read an allow-listed attribute of ``value``.

    For a language value, looks ``name`` up in ATTRIBUTES[kind_of(value)].
    For a host value, looks it up in host.attributes_of(value). Raises
    EvaluationError if it is not there. Methods are returned as Builtins
    bound to ``value``, so ``m.items()`` gives a tuple of pairs. Plain
    attribute values pass through freeze.
    """
    kind = kind_of(value)
    if kind is not None:
        if name not in ATTRIBUTES[kind]:
            raise EvaluationError.at(node, filename, f"{kind} has no attribute {name!r}")
        return _method(value, kind, name)
    allowed = host.attributes_of(value)
    if allowed is None or name not in allowed:
        raise EvaluationError.at(node, filename, f"{_type_name(value)} has no attribute {name!r}")
    # ``name`` is on the host's list for this exact type, checked above.
    attribute = getattr(value, name)
    if inspect.ismethod(attribute) or inspect.isbuiltin(attribute):
        return Builtin(f"{type(value).__name__}.{name}", attribute)
    try:
        return freeze(attribute, host)
    except (TypeError, ValueError) as error:
        raise EvaluationError.at(node, filename, str(error)) from None
