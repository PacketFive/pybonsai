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

from .limits import Limits
from .values import FrozenMap


def build_prelude() -> FrozenMap:
    """Return a FrozenMap from each file-visible name to its Builtin.

    ``pb_len`` is exposed as ``len``, and so on. ``range`` is marked as
    taking limits, so the evaluator passes them in.
    """
    raise NotImplementedError


def pb_len(value: object) -> int:
    raise NotImplementedError


def pb_range(*args: int, limits: Limits) -> tuple[int, ...]:
    """Like range, returned as a tuple.

    Bounds must be ints. The length is computed first and checked against
    ``limits.max_collection_len`` before the tuple is built.
    """
    raise NotImplementedError


def pb_sorted(values: object, *, reverse: bool = False) -> tuple[object, ...]:
    raise NotImplementedError


def pb_min(*values: object) -> object:
    raise NotImplementedError


def pb_max(*values: object) -> object:
    raise NotImplementedError


def pb_sum(values: object, start: int | float = 0) -> int | float:
    """Numbers only. Summing strings or tuples is rejected; use ``"".join``."""
    raise NotImplementedError


def pb_any(values: object) -> bool:
    raise NotImplementedError


def pb_all(values: object) -> bool:
    raise NotImplementedError


def pb_abs(value: int | float) -> int | float:
    raise NotImplementedError


def pb_str(value: object) -> str:
    """str() of a string, number, bool or None.

    A host value uses its type's ``__str__``. Any other value is a TypeError,
    so tuples and mappings cannot be turned into text with Python's repr.
    """
    raise NotImplementedError


def pb_int(value: object) -> int:
    raise NotImplementedError


def pb_bool(value: object) -> bool:
    raise NotImplementedError


def pb_enumerate(values: object, start: int = 0) -> tuple[tuple[int, object], ...]:
    raise NotImplementedError


def pb_zip(*iterables: object) -> tuple[tuple[object, ...], ...]:
    raise NotImplementedError


def pb_reversed(values: object) -> tuple[object, ...]:
    raise NotImplementedError
