# SPDX-License-Identifier: GPL-2.0
"""What an embedding program adds to the language.

PyBonsai knows nothing about packages or builds. A program that embeds it,
such as Lattice, describes its additions with a Host:

* ``names`` are the functions a file can call besides its own, normally
  the prelude plus the program's own functions.
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

from .values import Builtin, FrozenMap


@dataclass(frozen=True)
class Host:
    """The names and value types an embedding program exposes to files."""

    names: FrozenMap
    types: FrozenMap

    def __post_init__(self) -> None:
        """Validate the host.

        Every name in ``names`` is an identifier that does not start with
        ``_`` and maps to a Builtin. Every key of ``types`` is a class and
        maps to a frozenset of attribute names, none starting with ``_``.
        Raises ValueError or TypeError naming the bad entry.
        """
        raise NotImplementedError

    def attribute_names(self) -> frozenset[str]:
        """Every attribute name readable on at least one host type.

        The checker adds these to the language attribute allow list.
        """
        raise NotImplementedError

    def attributes_of(self, value: object) -> frozenset[str] | None:
        """The attributes readable on ``value``, or None if it is not a host value.

        Matches on the exact type, not on subclasses, so a subclass must be
        registered on its own.
        """
        raise NotImplementedError


def make_host(
    names: Mapping[str, Builtin] | None = None,
    types: Mapping[type, frozenset[str]] | None = None,
    include_prelude: bool = True,
) -> Host:
    """Build a Host from plain mappings.

    With ``include_prelude`` the prelude functions are added first. A name
    in ``names`` that repeats a prelude name raises ValueError, so a host
    cannot silently replace ``len`` or ``range``.
    """
    raise NotImplementedError


def default_host() -> Host:
    """The prelude only, with no host types. Used when no host is given."""
    raise NotImplementedError
