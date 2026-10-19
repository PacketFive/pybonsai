# SPDX-License-Identifier: GPL-2.0
"""Evaluator tests: RFC 0001 sections 7.2, 7.3, 7.6 and 7.7."""

import pytest

from pybonsai import (
    EvaluationError,
    FrozenMap,
    LimitExceeded,
    evaluate_source,
)

pytestmark = pytest.mark.xfail(raises=NotImplementedError, reason="not implemented yet")


def test_collections_are_immutable() -> None:
    result = evaluate_source("a = [1, 2]\nb = {'k': 1}\nc = {2, 1}")
    assert result["a"] == (1, 2)
    assert isinstance(result["b"], FrozenMap)
    assert result["c"] == frozenset({1, 2})


def test_set_iteration_is_sorted() -> None:
    result = evaluate_source("xs = [x for x in {'b', 'c', 'a'}]")
    assert result["xs"] == ("a", "b", "c")


def test_mapping_methods_return_tuples() -> None:
    result = evaluate_source("m = {'a': 1}\nks = m.keys()\nits = m.items()")
    assert result["ks"] == ("a",)
    assert result["its"] == (("a", 1),)


def test_only_file_names_are_returned() -> None:
    result = evaluate_source("x = len((1, 2))")
    assert tuple(result.keys()) == ("x",)
    assert result["x"] == 2


def test_function_call_and_defaults() -> None:
    result = evaluate_source("def f(a, b=10):\n    return a + b\nx = f(1)\ny = f(1, b=2)")
    assert (result["x"], result["y"]) == (11, 3)


def test_python_builtins_are_not_in_scope() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("x = open")


def test_unknown_name() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("x = y")


def test_recursion_is_rejected() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("def f(n):\n    return f(n)\nx = f(1)")


def test_mutual_recursion_is_rejected() -> None:
    source = "def f(n):\n    return g(n)\ndef g(n):\n    return f(n)\nx = f(1)"
    with pytest.raises(EvaluationError):
        evaluate_source(source)


def test_percent_formatting_on_strings_is_rejected() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("x = '%s' % 'a'")


def test_percent_on_ints_is_modulo() -> None:
    assert evaluate_source("x = 7 % 3")["x"] == 1


def test_attribute_on_wrong_type() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("x = (1, 2).lower()")


def test_duplicate_computed_key() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("k = 'a'\nm = {k: 1, 'a': 2}")


def test_huge_power_is_rejected_before_computing() -> None:
    with pytest.raises(LimitExceeded) as info:
        evaluate_source("x = 10 ** 10 ** 8")
    assert info.value.limit == "max_int_bits"


def test_huge_string_repeat_is_rejected() -> None:
    with pytest.raises(LimitExceeded) as info:
        evaluate_source("x = 'a' * 10 ** 9")
    assert info.value.limit == "max_str_len"
