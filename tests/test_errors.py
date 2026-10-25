# SPDX-License-Identifier: GPL-2.0
"""Error tests: RFC 0001 sections 7.2 and 7.7."""

import ast

import pytest

from pybonsai.errors import (
    EvaluationError,
    LimitExceeded,
    PyBonsaiError,
    RejectedSyntax,
    _position,
)


def first_expr(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


def test_rejected_syntax_names_node_and_reason() -> None:
    node = first_expr("(\n    open('f'))")
    err = RejectedSyntax.at(node, "x.pyb", "builtins are not in scope")
    assert err.msg == "Call is not permitted: builtins are not in scope"
    assert (err.filename, err.lineno, err.offset) == ("x.pyb", 2, 5)


def test_rejected_syntax_is_syntax_error_and_pybonsai_error() -> None:
    err = RejectedSyntax.at(first_expr("a"), "x.pyb", "reason")
    assert isinstance(err, SyntaxError)
    assert isinstance(err, PyBonsaiError)


def test_rejected_syntax_without_position() -> None:
    err = RejectedSyntax.at(ast.Add(), "x.pyb", "reason")
    assert err.lineno is None
    assert err.offset is None


def test_position_of_node_without_position() -> None:
    assert _position(ast.Load()) == (None, None)


def test_evaluation_error_keeps_zero_based_column() -> None:
    node = first_expr("(\n  y)")
    err = EvaluationError.at(node, "x.pyb", "unknown name 'y'")
    assert (err.lineno, err.col_offset) == (2, 2)
    assert str(err) == "x.pyb:2:3: unknown name 'y'"


@pytest.mark.parametrize(
    ("lineno", "col_offset", "expected"),
    [
        (4, 0, "x.pyb:4:1: boom"),
        (4, None, "x.pyb:4: boom"),
        (None, None, "x.pyb: boom"),
    ],
)
def test_evaluation_error_str(lineno: int | None, col_offset: int | None, expected: str) -> None:
    assert str(EvaluationError("boom", "x.pyb", lineno, col_offset)) == expected


def test_limit_exceeded_carries_limit_name() -> None:
    err = LimitExceeded("max_int_bits", "integer too large", "x.pyb", 1, 0)
    assert isinstance(err, EvaluationError)
    assert err.limit == "max_int_bits"
    assert str(err) == "x.pyb:1:1: integer too large"


def test_limit_exceeded_is_caught_as_evaluation_error() -> None:
    with pytest.raises(EvaluationError):
        raise LimitExceeded("max_steps", "too many steps", "x.pyb")
