# SPDX-License-Identifier: GPL-2.0
"""Pure helper functions available to every PyBonsai file (RFC 0001 section 7.6).

These are the language-level part of the standard library: ``len``,
``range``, ``sorted``, ``min``, ``max``, ``sum``, ``any``, ``all``, ``abs``,
``str``, ``int``, ``bool``, ``enumerate``, ``zip`` and ``reversed``. Each
has the usual Python meaning restricted to immutable values, and returns a
fully evaluated tuple where Python would return an iterator.

They are ordinary Python functions named ``pb_<name>`` so that they never
shadow Python's own builtins inside this package. ``sorted``, ``min`` and
``max`` take no ``key`` argument, because calling a PyBonsai function from
here would need the evaluator.
"""

from __future__ import annotations

from .limits import LimitReached, Limits
from .values import Builtin, FrozenMap, ordered

_NUMBERS = (int, float, bool)
_LANGUAGE_TYPES = (tuple, FrozenMap, frozenset)


def _is_number(value: object) -> bool:
    return type(value) in _NUMBERS


def _collection(values: object) -> tuple[object, ...]:
    return ordered(values)


def build_prelude() -> FrozenMap:
    """Return a FrozenMap from each file-visible name to its Builtin.

    ``pb_len`` is exposed as ``len``, and so on. ``range``
    and ``int`` are marked as taking limits, so the evaluator passes them in.
    """
    takes = {"range", "int"}
    functions = {
        "len": pb_len,
        "range": pb_range,
        "sorted": pb_sorted,
        "min": pb_min,
        "max": pb_max,
        "sum": pb_sum,
        "any": pb_any,
        "all": pb_all,
        "abs": pb_abs,
        "str": pb_str,
        "int": pb_int,
        "bool": pb_bool,
        "enumerate": pb_enumerate,
        "zip": pb_zip,
        "reversed": pb_reversed,
    }
    return FrozenMap(
        {name: Builtin(name, impl, takes_limits=name in takes) for name, impl in functions.items()}
    )


def pb_len(value: object) -> int:
    """Return the length of a string, tuple, FrozenMap or frozenset."""
    if type(value) not in (str, *_LANGUAGE_TYPES):
        raise TypeError("len() needs a string or a collection")
    return len(value)  # type: ignore[arg-type]


def pb_range(*args: int, limits: Limits) -> tuple[int, ...]:
    """Return ``range(*args)`` as a tuple.

    Bounds must be ints. The length is computed first and checked against
    ``limits.max_collection_len`` before the tuple is built.
    """
    if not 1 <= len(args) <= 3 or any(type(arg) is not int for arg in args):
        raise TypeError("range() needs one to three ints")
    span = range(*args)
    try:
        too_long = len(span) > limits.max_collection_len
    except OverflowError:
        too_long = True
    if too_long:
        raise LimitReached("max_collection_len", f"range longer than {limits.max_collection_len}")
    return tuple(span)


def pb_sorted(values: object, *, reverse: bool = False) -> tuple[object, ...]:
    """Return the items sorted as a tuple; mixed types are a TypeError."""
    if type(reverse) is not bool:
        raise TypeError("sorted() reverse must be a bool")
    return tuple(sorted(_collection(values), reverse=reverse))  # type: ignore[type-var]


def pb_min(*values: object) -> object:
    """Return the smallest of the arguments, or of one collection argument."""
    items = _collection(values[0]) if len(values) == 1 else values
    if not items:
        raise ValueError("min() of an empty collection")
    return min(items)  # type: ignore[type-var]


def pb_max(*values: object) -> object:
    """Return the largest of the arguments, or of one collection argument."""
    items = _collection(values[0]) if len(values) == 1 else values
    if not items:
        raise ValueError("max() of an empty collection")
    return max(items)  # type: ignore[type-var]


def pb_sum(values: object, start: int | float = 0) -> int | float:
    """Add numbers only; summing strings or tuples is rejected (use ``"".join``)."""
    items = _collection(values)
    if not _is_number(start) or not all(_is_number(item) for item in items):
        raise TypeError("sum() adds numbers only; use str.join for strings")
    return sum(items, start)  # type: ignore[arg-type]


def pb_any(values: object) -> bool:
    """Return True if any item of a collection is true."""
    return any(pb_bool(item) for item in _collection(values))


def pb_all(values: object) -> bool:
    """Return True if every item of a collection is true."""
    return all(pb_bool(item) for item in _collection(values))


def pb_abs(value: int | float) -> int | float:
    """Return the absolute value of a number."""
    if not _is_number(value):
        raise TypeError("abs() needs a number")
    return abs(value)


def pb_str(value: object) -> str:
    """Return str() of a string, number, bool or None.

    A host value uses its type's ``__str__``. Any other value is a TypeError,
    so tuples and mappings cannot be turned into text with Python's repr.
    """
    if type(value) in (str, int, float, bool, type(None)):
        return str(value)
    kind = type(value)
    if kind in _LANGUAGE_TYPES or kind.__str__ is object.__str__:
        raise TypeError(f"a {kind.__name__} cannot be converted to a string")
    return str(value)


def pb_int(value: object, *, limits: Limits) -> int:
    """Convert a string, bool or float to int; floats are truncated as in Python.

    A string with more digits than ``limits.max_int_bits`` allows is refused
    before conversion, so the result does not depend on the interpreter's
    own digit limit.
    """
    kind = type(value)
    if kind is int:
        return value  # type: ignore[return-value]
    if kind is bool or kind is float:
        return int(value)  # type: ignore[arg-type]
    if kind is str:
        assert isinstance(value, str)  # noqa: S101
        # A decimal digit carries more than three bits, so this bound is safe.
        if len(value.strip().replace("_", "").lstrip("+-")) > limits.max_int_bits // 3 + 1:
            raise LimitReached("max_int_bits", f"integer larger than {limits.max_int_bits} bits")
        return int(value)
    raise TypeError(f"int() cannot convert a {kind.__name__}")


def pb_bool(value: object) -> bool:
    """Return the truth value of a PyBonsai value."""
    return bool(value)


def pb_enumerate(values: object, start: int = 0) -> tuple[tuple[int, object], ...]:
    """Return ``(index, item)`` pairs as a tuple, counting from ``start``."""
    if type(start) is not int:
        raise TypeError("enumerate() start must be an int")
    return tuple(enumerate(_collection(values), start))


def pb_zip(*iterables: object) -> tuple[tuple[object, ...], ...]:
    """Return tuples of corresponding items, stopping at the shortest collection."""
    return tuple(zip(*(_collection(values) for values in iterables), strict=False))


def pb_reversed(values: object) -> tuple[object, ...]:
    """Return the items of a tuple or string in reverse order as a tuple."""
    if type(values) not in (str, tuple):
        raise TypeError("reversed() needs a string or a tuple")
    return tuple(reversed(values))  # type: ignore[arg-type]
