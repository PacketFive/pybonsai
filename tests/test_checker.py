# SPDX-License-Identifier: GPL-2.0
"""Checker tests: RFC 0001 sections 7.3 to 7.5.

Each rejected snippet is one rule. A test that hits NotImplementedError is
reported as xfail; once the code exists, a wrong answer is a real failure.
"""

import pytest

from pybonsai.checker import check
from pybonsai.errors import RejectedSyntax
from pybonsai.parser import parse

pytestmark = pytest.mark.xfail(raises=NotImplementedError, reason="not implemented yet")


def check_source(source: str) -> None:
    check(parse(source, "<test>"), "<test>")


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("while True:\n    x = 1", id="while"),
        pytest.param("import os", id="import"),
        pytest.param("from os import path", id="import-from"),
        pytest.param("x = 1\nx = 2", id="reassign"),
        pytest.param("x = 1\nx += 1", id="augassign"),
        pytest.param("x: int = 1", id="annassign"),
        pytest.param("x = 1\ndel x", id="delete"),
        pytest.param("x = ().__class__", id="dunder"),
        pytest.param("x = 'a'._private", id="underscore"),
        pytest.param("x = '{0.__class__}'.format(1)", id="str-format"),
        pytest.param("x = 'a'.encode()", id="unlisted-attr"),
        pytest.param("class A:\n    x = 1", id="class"),
        pytest.param("def f():\n    yield 1", id="generator"),
        pytest.param("x = (i for i in ())", id="genexp"),
        pytest.param("async def f():\n    return 1", id="async"),
        pytest.param("try:\n    x = 1\nexcept Exception:\n    y = 2", id="try"),
        pytest.param("with a as b:\n    x = 1", id="with"),
        pytest.param("assert 1", id="assert"),
        pytest.param("raise ValueError", id="raise"),
        pytest.param("x = b'bytes'", id="bytes"),
        pytest.param("x = 1j", id="complex"),
        pytest.param("x = ...", id="ellipsis"),
        pytest.param("y = 1\nx = f'{y!r}'", id="fstring-conversion"),
        pytest.param("y = 1\nx = f'{y:>4}'", id="fstring-spec"),
        pytest.param("x = {'a': 1, 'a': 2}", id="duplicate-key"),
        pytest.param("@d\ndef f():\n    return 1", id="decorator"),
        pytest.param("def f[T](x):\n    return x", id="type-params"),
        pytest.param("type X = int", id="type-alias"),
        pytest.param("x = (y := 1)", id="walrus"),
        pytest.param("match 1:\n    case 1:\n        x = 1", id="match"),
        pytest.param("x = 1 << 2", id="shift"),
        pytest.param("x.y = 1", id="attribute-target"),
        pytest.param("for i in ():\n    x = i\nelse:\n    y = 1", id="for-else"),
    ],
)
def test_rejected(source: str) -> None:
    with pytest.raises(RejectedSyntax):
        check_source(source)


def test_rejection_names_node_and_position() -> None:
    with pytest.raises(RejectedSyntax) as info:
        check_source("x = 1\nwhile True:\n    y = 1")
    assert "While" in str(info.value)
    assert info.value.lineno == 2
    assert info.value.filename == "<test>"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "src = fetch_url(url='https://example.org/a.tar.gz', sha256='0' * 64)\n"
            "pkg = derivation(name='a-1', builder='/bin/sh', args=['-c', 'true'],\n"
            "                 env={'src': src}, outputs=['out'])",
            id="rfc-example",
        ),
        pytest.param("xs = [i * 2 for i in range(3) if i]", id="listcomp"),
        pytest.param("m = {k: v for k, v in (('a', 1),)}", id="dictcomp"),
        pytest.param("def f(a, *, b=1):\n    return a + b\nx = f(1, b=2)", id="function"),
        pytest.param("g = lambda x: x + 1", id="lambda"),
        pytest.param("a, b = (1, 2)", id="unpack"),
        pytest.param("n = 'x'\ns = f'{n}-1'", id="fstring"),
        pytest.param("x = 1 if True else 2", id="ifexp"),
        pytest.param("for i in (1, 2):\n    y = i", id="for-rebinds-per-iteration"),
        pytest.param("x = 1\ndef f():\n    x = 2\n    return x", id="shadow-in-function"),
    ],
)
def test_accepted(source: str) -> None:
    check_source(source)
