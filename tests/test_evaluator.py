# SPDX-License-Identifier: GPL-2.0
"""Evaluator tests: RFC 0001 sections 7.2, 7.3, 7.6 and 7.7."""

import pytest

from pybonsai import (
    EvaluationError,
    FrozenMap,
    LimitExceeded,
    evaluate_source,
)


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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x = 1 + 2 * 3 - 4 // 3 % 2", 6),
        ("x = 7 / 2", 3.5),
        ("x = -(+3)", -3),
        ("x = not ()", True),
        ("x = 0 or '' or 'a'", "a"),
        ("x = 1 and 0 and 2", 0),
        ("x = 1 < 2 < 3", True),
        ("x = 1 < 3 < 2", False),
        ("x = 'a' in {'a': 1}", True),
        ("x = 2 not in (1, 2)", False),
        ("x = None is None", True),
        ("x = 1 is not None", True),
        ("x = 'abc'[1:]", "bc"),
        ("x = (1, 2, 3)[::-1]", (3, 2, 1)),
        ("x = {'a': 1}['a']", 1),
        ("x = (1, *(2, 3))", (1, 2, 3)),
        ("x = {1, *(2,)}", frozenset({1, 2})),
        ("x = {**{'a': 1}, 'b': 2}", {"a": 1, "b": 2}),
        ("a, (b, c) = (1, (2, 3))\nx = a + b + c", 6),
        ("a = b = 2\nx = a * b", 4),
        ("x = {k: v for k, v in {'a': 1}.items()}", {"a": 1}),
        ("x = [(i, j) for i in range(2) for j in range(i)]", ((1, 0),)),
        ("x = (lambda a, b=2: a * b)(3)", 6),
        (
            "def f(*args, **kw):\n    return (args, kw)\nx = f(1, 2, a=3)",
            ((1, 2), FrozenMap({"a": 3})),
        ),
        ("def f(a, /, b, *, c):\n    return a + b + c\nx = f(1, b=2, c=3)", 6),
        ("def f(a, *, c=5):\n    return a + c\nx = f(*(1,), **{'c': 2})", 3),
        ("def f():\n    for i in (1, 2):\n        return i\nx = f()", 1),
        ("def f():\n    return\nx = f()", None),
        ("def f():\n    y = 1\nx = f()", None),
        ("def f(n):\n    return n\ng = f\nx = g(2)", 2),
        ("x = f'{1}-{True}-{None}-{1.5}'", "1-True-None-1.5"),
        ("def mk():\n    return lambda: 1\nx = mk()()", 1),
    ],
)
def test_expressions(source: str, expected: object) -> None:
    result = evaluate_source(source)["x"]
    if isinstance(expected, dict):
        expected = FrozenMap(expected)
    assert result == expected


@pytest.mark.parametrize(
    "source",
    [
        "x = 1 / 0",
        "x = (-8) ** 0.5",
        "x = 'a' + 1",
        "x = len + 1",
        "x = -'a'",
        "x = 1 in 2",
        "x = 1 < 'a'",
        "x = (1, 2)[5]",
        "x = (1, 2)['a']",
        "x = {'a': 1}['b']",
        "x = 1[0]",
        "x = 'ab'[1.5:]",
        "x = {**(1,)}",
        "x = len(**(1,))",
        "x = len(*1)",
        "x = 1()",
        "a, b = (1, 2, 3)",
        "def f(a):\n    return a\nx = f()",
        "def f(a):\n    return a\nx = f(1, 2)",
        "def f(a):\n    return a\nx = f(1, a=2)",
        "def f(a):\n    return a\nx = f(b=2)",
        "def f(a, /):\n    return a\nx = f(a=1)",
        "def f(*, a):\n    return a\nx = f()",
        "def f(**k):\n    return k\nx = f(**{1: 2})",
        "def f(**k):\n    return k\nx = f(a=1, **{'a': 2})",
        "x = f'{(1,)}'",
        "x = f'{len}'",
        "x = {(1,): 1, (1,): 2}",
        "x = {k: 1 for k in (1, 1)}",
        "def f():\n    g = lambda: f()\n    return g()\nx = f()",
        "def outer():\n    def inner(n):\n        return outer()\n    return inner(1)\nx = outer()",
    ],
)
def test_evaluation_errors(source: str) -> None:
    with pytest.raises(EvaluationError):
        evaluate_source(source)


def test_error_position() -> None:
    with pytest.raises(EvaluationError) as info:
        evaluate_source("x = 1\ny = (1, 2)[x + 5]")
    assert info.value.lineno == 2
    assert str(info.value).startswith("<string>:2:")


def test_set_order_does_not_depend_on_hash_seed() -> None:
    import os
    import subprocess
    import sys

    source = (
        "x = '-'.join({'c', 'a', 'b', 'e', 'd'})\n"
        "y = sum({0.1, 0.2, 0.3, 1e16})\n"
        "z = [len(s) for s in {{1, 2}, {3}, {4, 5, 6}}]"
    )
    program = (
        f"from pybonsai import evaluate_source as e\nr = e({source!r})\n"
        "print(r['x'], r['y'], r['z'])"
    )
    outputs = set()
    for seed in ("1", "2", "3", "4"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run(  # noqa: S603
            [sys.executable, "-c", program], env=env, capture_output=True, text=True, check=True
        )
        outputs.add(done.stdout)
    assert len(outputs) == 1
    assert outputs.pop().startswith("a-b-c-d-e ")


def test_functions_capture_their_scope() -> None:
    result = evaluate_source(
        "def adder(n):\n    return lambda x: x + n\nadd2 = adder(2)\nadd3 = adder(3)\n"
        "x = (add2(1), add3(1))"
    )
    assert result["x"] == (3, 4)


def test_for_body_names_stay_inside() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("for i in (1,):\n    y = i\nz = y")


def test_evaluate_file(tmp_path) -> None:
    from pybonsai import evaluate_file

    path = tmp_path / "a.pyb"
    path.write_text("x = 'é'\n", encoding="utf-8")
    assert evaluate_file(path)["x"] == "é"
    path.write_text("x = y\n", encoding="utf-8")
    with pytest.raises(EvaluationError) as info:
        evaluate_file(path)
    assert info.value.filename == str(path)
