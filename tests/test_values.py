# SPDX-License-Identifier: GPL-2.0
"""Value model tests: RFC 0001 sections 7.3 and 7.5."""

import ast
import copy
import pickle

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pybonsai import EvaluationError, FrozenMap, default_host
from pybonsai.values import canonical_key, freeze, iterate, kind_of, ordered, type_name

NODE = ast.Constant(value=1, lineno=1, col_offset=0)


def test_frozenmap_is_read_only() -> None:
    m = FrozenMap({"a": 1})
    with pytest.raises(AttributeError):
        m.x = 1  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        del m._data  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        m["b"] = 2  # type: ignore[index]


def test_frozenmap_copies_its_source() -> None:
    source = {"a": 1}
    m = FrozenMap(source)
    source["a"] = 2
    assert m["a"] == 1


def test_frozenmap_views_are_tuples() -> None:
    m = FrozenMap({"b": 2, "a": 1})
    assert m.keys() == ("b", "a")
    assert m.values() == (2, 1)
    assert m.items() == (("b", 2), ("a", 1))
    assert m.get("c", 3) == 3
    assert "a" in m and len(m) == 2
    assert repr(m) == "FrozenMap({'b': 2, 'a': 1})"


def test_frozenmap_equality_ignores_order_but_not_type() -> None:
    assert FrozenMap({"a": 1, "b": 2}) == FrozenMap({"b": 2, "a": 1})
    assert FrozenMap({"a": 1}) != FrozenMap({"a": 2})
    assert FrozenMap({"a": 1}) != {"a": 1}


def test_frozenmap_copy_and_pickle() -> None:
    m = FrozenMap({"a": (1, 2)})
    assert copy.deepcopy(m) == m
    assert pickle.loads(pickle.dumps(m)) == m  # noqa: S301


@given(st.dictionaries(st.text(max_size=3), st.integers()))
def test_frozenmap_hash_matches_equality(data: dict[str, int]) -> None:
    forward = FrozenMap(data)
    backward = FrozenMap(dict(reversed(list(data.items()))))
    assert forward == backward
    assert hash(forward) == hash(backward)


def test_kind_of_matches_exact_types() -> None:
    assert kind_of("a") == "str"
    assert kind_of(()) == "tuple"
    assert kind_of(FrozenMap()) == "mapping"
    assert kind_of(frozenset()) == "frozenset"
    assert kind_of(1) is None

    class Named(tuple):
        __slots__ = ()

    assert kind_of(Named()) is None


def test_freeze_converts_mutable_values() -> None:
    frozen = freeze({"a": [1, {2}], "b": {"c": None}}, default_host())
    assert frozen == FrozenMap({"a": (1, frozenset({2})), "b": FrozenMap({"c": None})})


def test_freeze_rejects_unknown_types_and_cycles() -> None:
    with pytest.raises(TypeError):
        freeze(object(), default_host())
    loop: list[object] = []
    loop.append(loop)
    with pytest.raises(ValueError):
        freeze(loop, default_host())


def test_ordered_sorts_sets() -> None:
    assert ordered(frozenset({"b", "a"})) == ("a", "b")
    assert ordered("ab") == ("a", "b")
    assert ordered(frozenset({"a", 2, None, (1,), 1.5})) == (None, 1.5, 2, "a", (1,))
    with pytest.raises(TypeError):
        ordered(1)


def test_canonical_order_is_total() -> None:
    inner = [frozenset({1}), frozenset({2}), frozenset({1, 2}), frozenset()]
    nan = float("nan")
    assert ordered(frozenset(inner)) == (
        frozenset(),
        frozenset({1}),
        frozenset({1, 2}),
        frozenset({2}),
    )
    assert ordered(frozenset({nan, 1.0}))[0] == 1.0
    maps = frozenset({FrozenMap({"b": 1}), FrozenMap({"a": 2})})
    assert ordered(maps) == (FrozenMap({"a": 2}), FrozenMap({"b": 1}))


def test_canonical_order_rejects_functions() -> None:
    builtin = default_host().names["len"]
    with pytest.raises(TypeError):
        canonical_key(builtin)
    with pytest.raises(TypeError):
        canonical_key(object())


def test_iterate_reports_position() -> None:
    with pytest.raises(EvaluationError) as info:
        iterate(1, NODE, "<test>")
    assert info.value.lineno == 1


def test_type_name() -> None:
    assert type_name(None) == "None"
    assert type_name(1) == "int"
    assert type_name(FrozenMap()) == "mapping"
