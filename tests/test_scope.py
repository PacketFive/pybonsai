# SPDX-License-Identifier: GPL-2.0
"""Scope tests: single assignment and lookup order."""

import ast

import pytest

from pybonsai import EvaluationError
from pybonsai.scope import Scope

NODE = ast.Name(id="x", lineno=3, col_offset=4)


def test_define_and_lookup() -> None:
    outer = Scope(names={"x": 1})
    inner = outer.child()
    inner.define("y", 2, NODE, "<test>")
    assert inner.lookup("x", NODE, "<test>") == 1
    assert inner.lookup("y", NODE, "<test>") == 2
    assert inner.local_names() == {"y": 2}


def test_inner_scope_may_shadow() -> None:
    outer = Scope(names={"x": 1})
    inner = outer.child()
    inner.define("x", 2, NODE, "<test>")
    assert inner.lookup("x", NODE, "<test>") == 2


def test_redefinition_is_rejected() -> None:
    scope = Scope()
    scope.define("x", 1, NODE, "<test>")
    with pytest.raises(EvaluationError):
        scope.define("x", 2, NODE, "<test>")


def test_unknown_name_has_position() -> None:
    with pytest.raises(EvaluationError) as info:
        Scope().lookup("len", NODE, "<test>")
    assert (info.value.lineno, info.value.col_offset) == (3, 4)
