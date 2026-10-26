# SPDX-License-Identifier: GPL-2.0
"""Prelude tests: RFC 0001 section 7.6."""

import pytest

from pybonsai import EvaluationError, FrozenMap, LimitExceeded, Limits, evaluate_source


def run(expression: str, limits: Limits | None = None) -> object:
    if limits is None:
        return evaluate_source(f"x = {expression}")["x"]
    return evaluate_source(f"x = {expression}", limits=limits)["x"]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("len('abc')", 3),
        ("len({'a': 1})", 1),
        ("range(3)", (0, 1, 2)),
        ("range(5, 0, -2)", (5, 3, 1)),
        ("sorted({3, 1, 2})", (1, 2, 3)),
        ("sorted((1, 3, 2), reverse=True)", (3, 2, 1)),
        ("min(3, 1, 2)", 1),
        ("max((3, 1, 2))", 3),
        ("min({'b', 'a'})", "a"),
        ("sum((1, 2, 3))", 6),
        ("sum((0.5, 0.5), 1)", 2.0),
        ("any((0, '', 1))", True),
        ("all(())", True),
        ("all((1, 0))", False),
        ("abs(-2)", 2),
        ("str(1.5)", "1.5"),
        ("str(None)", "None"),
        ("int('42')", 42),
        ("int(2.9)", 2),
        ("int(True)", 1),
        ("bool(())", False),
        ("bool({'a': 1})", True),
        ("enumerate(('a', 'b'), 1)", ((1, "a"), (2, "b"))),
        ("zip((1, 2, 3), 'ab')", ((1, "a"), (2, "b"))),
        ("reversed((1, 2))", (2, 1)),
        ("reversed('ab')", ("b", "a")),
        ("'-'.join({'b', 'a'})", "a-b"),
        ("'aXa'.replace('a', 'bb')", "bbXbb"),
        ("{1, 2}.union((3,))", frozenset({1, 2, 3})),
        ("'a b'.split()", ("a", "b")),
    ],
)
def test_prelude_values(expression: str, expected: object) -> None:
    result = run(expression)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "len(1)",
        "range(1.5)",
        "range()",
        "range(1, 2, 0)",
        "sorted((1, 'a'))",
        "sorted((1,), reverse=1)",
        "min(())",
        "max(())",
        "sum(('a', 'b'), '')",
        "abs('a')",
        "str((1,))",
        "str(len)",
        "int('x')",
        "int((1,))",
        "enumerate((), 'a')",
        "reversed({1})",
        "'-'.join((1, 2))",
        "'a'.replace(1, 'b')",
        "range(3, limits=1)",
        "len(1, 2)",
    ],
)
def test_prelude_errors(expression: str) -> None:
    with pytest.raises(EvaluationError):
        run(expression)


@pytest.mark.parametrize(
    ("expression", "limit"),
    [
        ("range(10 ** 9)", "max_collection_len"),
        ("range(10 ** 30)", "max_collection_len"),
        ("'x' * 900 + ''.join(('y',) * 200)", "max_str_len"),
        ("('ab' * 600).replace('a', 'aaaa')", "max_str_len"),
        ("int('9' * 900)", "max_int_bits"),
    ],
)
def test_prelude_limits(expression: str, limit: str) -> None:
    limits = Limits(max_int_bits=1000, max_str_len=1000, max_collection_len=1000)
    with pytest.raises(LimitExceeded) as info:
        run(expression, limits)
    assert info.value.limit == limit


def test_mapping_get() -> None:
    assert run("{'a': 1}.get('b', 2)") == 2
    assert isinstance(run("{'a': {'b': 1}}"), FrozenMap)
