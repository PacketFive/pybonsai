# SPDX-License-Identifier: GPL-2.0
"""Limit tests: RFC 0001 section 7.7."""

import ast

import pytest

from pybonsai import LimitExceeded, Limits, evaluate_source
from pybonsai.limits import Budget

SMALL = Limits(
    max_int_bits=64,
    max_str_len=100,
    max_collection_len=100,
    max_call_depth=4,
    max_depth=40,
    max_nodes=10_000,
)


@pytest.mark.parametrize(
    ("source", "limit"),
    [
        ("x = 2 ** 64", "max_int_bits"),
        ("x = 3 ** 1000000000", "max_int_bits"),
        ("x = (2 ** 40) * (2 ** 40)", "max_int_bits"),
        ("x = 2 ** 63 + 2 ** 63", "max_int_bits"),
        ("x = 18446744073709551616", "max_int_bits"),
        ("x = 'a' * 101", "max_str_len"),
        ("x = 101 * 'a'", "max_str_len"),
        ("x = 'a' * 60 + 'b' * 60", "max_str_len"),
        ("s = 'a' * 60\nx = f'{s}{s}'", "max_str_len"),
        ("x = (1,) * 101", "max_collection_len"),
        ("x = (1,) * 60 + (2,) * 60", "max_collection_len"),
        ("x = [i for i in range(60) for j in range(2)]", "max_collection_len"),
        ("x = {(i, j): j for i in range(60) for j in range(2)}", "max_collection_len"),
        ("x = (*range(60), *range(60))", "max_collection_len"),
        ("x = [i for i in range(100) for j in range(100) for k in range(100) if 0]", "max_nodes"),
    ],
)
def test_limits(source: str, limit: str) -> None:
    with pytest.raises(LimitExceeded) as info:
        evaluate_source(source, limits=SMALL)
    assert info.value.limit == limit


def test_negative_and_small_powers_are_allowed() -> None:
    result = evaluate_source("a = 2 ** -1\nb = 1 ** 10 ** 9\nc = (-1) ** 10 ** 9", limits=SMALL)
    assert (result["a"], result["b"], result["c"]) == (0.5, 1, 1)


def test_call_depth() -> None:
    source = (
        "def a(x):\n    return x\n"
        "def b(x):\n    return a(x)\n"
        "def c(x):\n    return b(x)\n"
        "def d(x):\n    return c(x)\n"
        "def e(x):\n    return d(x)\n"
    )
    assert evaluate_source(source + "y = d(1)", limits=SMALL)["y"] == 1
    with pytest.raises(LimitExceeded) as info:
        evaluate_source(source + "y = e(1)", limits=SMALL)
    assert info.value.limit == "max_call_depth"


def test_nesting_depth() -> None:
    with pytest.raises(LimitExceeded) as info:
        evaluate_source("x = " + "-" * 50 + "1", limits=SMALL)
    assert info.value.limit == "max_depth"


def test_depth_is_restored_after_return() -> None:
    body = "".join(f"y{i} = f({i})\n" for i in range(60))
    result = evaluate_source("def f(n):\n    return n\n" + body, limits=SMALL)
    assert result["y59"] == 59


def test_deepest_file_never_hits_python_recursion_limit() -> None:
    # Each function nests as deeply as the default limits allow.
    nested = "-" * 20 + "x"
    source = "".join(
        f"def f{i}(x):\n    return {nested if i == 0 else f'f{i - 1}({nested})'}\n"
        for i in range(70)
    )
    with pytest.raises(LimitExceeded):
        evaluate_source(source + "y = f69(1)")
    with pytest.raises(LimitExceeded):
        evaluate_source("x = " + "-" * 190 + "1")


def test_budget_counts_nodes() -> None:
    budget = Budget(Limits(max_nodes=1), "<test>")
    node = ast.Constant(value=1)
    budget.charge_node(node)
    with pytest.raises(LimitExceeded):
        budget.charge_node(node)
