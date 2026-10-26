# SPDX-License-Identifier: GPL-2.0
"""Parser tests: RFC 0001 section 7.1."""

import sys

import pytest

from pybonsai import RejectedSyntax, parser
from pybonsai.parser import MAX_TREE_DEPTH, parse, require_supported_python


def test_parse_returns_module() -> None:
    assert parse("x = 1", "<test>").body


def test_syntax_error_becomes_rejected_syntax() -> None:
    with pytest.raises(RejectedSyntax) as info:
        parse("x = (", "<test>")
    assert info.value.filename == "<test>"
    assert isinstance(info.value, SyntaxError)


def test_newer_grammar_is_rejected() -> None:
    # Python 3.13 and later would accept this; 3.12 does not.
    with pytest.raises(RejectedSyntax):
        parse("x = 1\ndef f[T = int](): return 1", "<test>")


def test_deep_tree_is_rejected() -> None:
    source = "x = " + "-" * (MAX_TREE_DEPTH + 10) + "1"
    with pytest.raises(RejectedSyntax) as info:
        parse(source, "<test>")
    assert info.value.lineno == 1


def test_parser_limit_is_rejected() -> None:
    with pytest.raises(RejectedSyntax):
        parse("x = " + "(" * 1000 + ")" * 1000, "<test>")


def test_old_python_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    require_supported_python()
    monkeypatch.setattr(parser, "PYTHON_BASELINE", (sys.version_info[0], 99))
    with pytest.raises(RuntimeError):
        require_supported_python()
