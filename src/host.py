# SPDX-License-Identifier: GPL-2.0
"""What an embedding program adds to the language.

PyBonsai knows nothing about packages or builds. A program that embeds it,
such as Lattice, describes its additions with a Host:

* ``names`` are the functions a file can call besides its own, normally
  the prelude plus the program's own functions, and any constants the
  program gives the file, such as a mapping of options.
* ``types`` are the program's own value types, each with the attributes a
  file may read. Lattice registers ``Derivation`` here.

A host type MUST be immutable and hashable, because values are shared and
used as mapping keys. A file can interpolate a host value in an f-string
only if the type defines ``__str__``; Lattice uses it to give a store path.
The attributes listed for a type are read by the evaluator with a fixed
name already checked against the list, never with a name computed by the
file.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

from .values import _SCALARS, Builtin, FrozenMap


@dataclass(frozen=True)
class Host:
    """The names and value types an embedding program exposes to files."""

    names: FrozenMap
    types: FrozenMap

    def __post_init__(self) -> None:
        """Validate the host.

        Every name in ``names`` is an identifier that does not start with
        ``_`` and maps to a Builtin or to a PyBonsai value: a string,
        number, bool, None, tuple, frozenset, FrozenMap or host type
        instance, with only such values inside. Every key of ``types`` is a class and
        maps to a frozenset of attribute names, none starting with ``_``.
        Raises ValueError or TypeError naming the bad entry.
        """
        if type(self.names) is not FrozenMap or type(self.types) is not FrozenMap:
            raise TypeError("Host names and types must be FrozenMaps")
        for name, value in self.names.items():
            if type(name) is not str or not name.isidentifier() or name.startswith("_"):
                raise ValueError(f"host name {name!r} is not a public identifier")
            if type(value) is not Builtin and not _is_value(value, self.types):
                raise TypeError(f"host name {name!r} must map to a Builtin or a PyBonsai value")
        for kind, attributes in self.types.items():
            if not isinstance(kind, type):
                raise TypeError(f"host type {kind!r} is not a class")
            if kind.__hash__ is None:
                raise TypeError(f"host type {kind.__name__} is not hashable")
            if type(attributes) is not frozenset:
                raise TypeError(f"attributes of host type {kind.__name__} must be a frozenset")
            for attribute in attributes:
                if (
                    type(attribute) is not str
                    or not attribute.isidentifier()
                    or attribute.startswith("_")
                ):
                    raise ValueError(
                        f"attribute {attribute!r} of host type {kind.__name__} is not public"
                    )

    def attribute_names(self) -> frozenset[str]:
        """Every attribute name readable on at least one host type.

        The checker adds these to the language attribute allow list.
        """
        names: frozenset[str] = frozenset()
        for attributes in self.types.values():
            names |= attributes  # type: ignore[operator]
        return names

    def attributes_of(self, value: object) -> frozenset[str] | None:
        """Return the attributes readable on ``value``, or None for a non-host value.

        Matches on the exact type, not on subclasses, so a subclass must be
        registered on its own.
        """
        attributes = self.types.get(type(value))
        return attributes  # type: ignore[return-value]


def _is_value(value: object, types: FrozenMap) -> bool:
    """Return whether ``value`` is an immutable PyBonsai value a file may read."""
    kind = type(value)
    if kind in _SCALARS or kind in types:
        return True
    if kind is tuple or kind is frozenset:
        return all(_is_value(item, types) for item in value)  # type: ignore[attr-defined]
    if kind is FrozenMap:
        return all(
            _is_value(k, types) and _is_value(v, types)
            for k, v in value.items()  # type: ignore[attr-defined]
        )
    return False


def make_host(
    names: Mapping[str, object] | None = None,
    types: Mapping[type, frozenset[str]] | None = None,
    include_prelude: bool = True,
) -> Host:
    """Build a Host from plain mappings.

    With ``include_prelude`` the prelude functions are added first. A name
    in ``names`` that repeats a prelude name raises ValueError, so a host
    cannot silently replace ``len`` or ``range``. A value in ``names`` that
    is not a Builtin is passed through values.freeze first, so a dict or
    list given here reaches the file as a FrozenMap or tuple.
    """
    from .prelude import build_prelude
    from .values import freeze

    host_types = FrozenMap(dict(types or {}))
    probe = Host(FrozenMap(), host_types)
    combined: dict[object, object] = dict(build_prelude()) if include_prelude else {}
    for name, value in (names or {}).items():
        if name in combined:
            raise ValueError(f"host name {name!r} repeats a prelude name")
        combined[name] = value if type(value) is Builtin else freeze(value, probe)
    return Host(FrozenMap(combined), host_types)


@cache
def default_host() -> Host:
    """Return a host with the prelude only and no host types.

    The host is built once and shared, which is safe because it is immutable.
    """
    return make_host()
