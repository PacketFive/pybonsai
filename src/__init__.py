# SPDX-License-Identifier: GPL-2.0
"""PyBonsai, a hermetic subset of Python 3.12 (RFC 0001 section 7).

A file passes through three stages, each in its own module:

1. :func:`parser.parse` turns source text into a Python 3.12 syntax tree.
2. :class:`checker.Checker` rejects every construct outside the allow list
   before any part of the file is evaluated.
3. :class:`evaluator.Evaluator` walks the checked tree and returns the names
   the file defines.

PyBonsai has no knowledge of packages or builds. A program that embeds it
passes a :class:`host.Host` holding the functions and value types it adds.
Lattice is one such program. Without a host, a file sees only the prelude.

Example::

    from pybonsai import evaluate_source

    names = evaluate_source("xs = [i * i for i in range(4)]")
    assert names["xs"] == (0, 1, 4, 9)
"""

from __future__ import annotations

import os

from .checker import check
from .errors import EvaluationError, LimitExceeded, PyBonsaiError, RejectedSyntax
from .evaluator import Evaluator
from .host import Host, default_host, make_host
from .limits import DEFAULT_LIMITS, Limits
from .parser import parse, require_supported_python
from .values import Builtin, FrozenMap

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_LIMITS",
    "Builtin",
    "EvaluationError",
    "FrozenMap",
    "Host",
    "LimitExceeded",
    "Limits",
    "PyBonsaiError",
    "RejectedSyntax",
    "default_host",
    "evaluate_file",
    "evaluate_source",
    "make_host",
]


def evaluate_source(
    source: str,
    filename: str = "<string>",
    host: Host | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> FrozenMap:
    """Parse, check and evaluate PyBonsai source text.

    ``host`` defaults to default_host(). Returns a read-only mapping of
    every top-level name the file assigns, in assignment order. Host names
    are not included.

    Raises RejectedSyntax if the file uses a construct outside the allow
    list, EvaluationError if evaluation fails, and LimitExceeded if a limit
    from section 7.7 is reached. A file either evaluates completely or
    raises; there is no partial result.
    """
    require_supported_python()
    host = host if host is not None else default_host()
    tree = parse(source, filename)
    check(tree, filename, host.attribute_names())
    return Evaluator(filename, host, limits).evaluate_module(tree)


def evaluate_file(
    path: str | os.PathLike[str],
    host: Host | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> FrozenMap:
    """Read a ``.pyb`` file as UTF-8 and evaluate it with evaluate_source.

    The file is read here, before evaluation starts. The evaluator itself
    never touches the filesystem.
    """
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    return evaluate_source(source, os.fspath(path), host, limits)
