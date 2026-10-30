# SPDX-License-Identifier: GPL-2.0
"""Host tests: how an embedding program extends the language."""

from dataclasses import dataclass

import pytest

from pybonsai import (
    Builtin,
    EvaluationError,
    FrozenMap,
    Host,
    LimitExceeded,
    Limits,
    evaluate_source,
    make_host,
)
from pybonsai.host import default_host


@dataclass(frozen=True)
class Package:
    name: str
    version: str

    def __str__(self) -> str:
        return f"/store/{self.name}-{self.version}"


def make_package(name: str, version: str) -> Package:
    return Package(name, version)


def package_host() -> Host:
    return make_host(
        names={"package": Builtin("package", make_package)},
        types={Package: frozenset({"name", "version"})},
    )


def test_host_function_and_attributes() -> None:
    result = evaluate_source(
        "p = package('hello', '2.12')\nn = p.name\ns = f'{p}/bin'", host=package_host()
    )
    assert result["n"] == "hello"
    assert result["s"] == "/store/hello-2.12/bin"
    assert tuple(result.keys()) == ("p", "n", "s")


def test_unlisted_host_attribute_is_rejected() -> None:
    with pytest.raises(EvaluationError):
        evaluate_source("p = package('a', '1')\nx = p.name.version", host=package_host())


def test_host_attributes_reach_the_checker() -> None:
    assert package_host().attribute_names() == frozenset({"name", "version"})


def test_attributes_of_matches_exact_type() -> None:
    class Sub(Package):
        pass

    host = package_host()
    assert host.attributes_of(Package("a", "1")) == frozenset({"name", "version"})
    assert host.attributes_of(Sub("a", "1")) is None


def test_host_cannot_replace_prelude_names() -> None:
    with pytest.raises(ValueError):
        make_host(names={"len": Builtin("len", len)})


def test_host_without_prelude() -> None:
    host = make_host(include_prelude=False)
    with pytest.raises(EvaluationError):
        evaluate_source("x = len(())", host=host)


@pytest.mark.parametrize(
    ("names", "types", "error"),
    [
        ({"_x": Builtin("x", len)}, {}, ValueError),
        ({"x": len}, {}, TypeError),
        ({}, {"Package": frozenset()}, TypeError),
        ({}, {Package: {"name"}}, TypeError),
        ({}, {Package: frozenset({"_name"})}, ValueError),
        ({}, {list: frozenset()}, TypeError),
    ],
)
def test_host_validation(names: dict, types: dict, error: type[Exception]) -> None:
    with pytest.raises(error):
        Host(FrozenMap(names), FrozenMap(types))


def test_host_fields_must_be_frozenmaps() -> None:
    with pytest.raises(TypeError):
        Host({}, FrozenMap())  # type: ignore[arg-type]


def test_default_host_is_shared() -> None:
    assert default_host() is default_host()


def test_host_constants_are_readable() -> None:
    host = make_host(
        names={"config": {"DEBUG": True, "LEVELS": [1, 2]}, "release": "1.0"},
        types={Package: frozenset({"name", "version"})},
    )
    result = evaluate_source(
        "debug = config.get('DEBUG', False)\n"
        "missing = config.get('OTHER', 3)\n"
        "levels = config['LEVELS']\n"
        "r = release",
        host=host,
    )
    assert result["debug"] is True
    assert result["missing"] == 3
    assert result["levels"] == (1, 2)
    assert result["r"] == "1.0"
    assert tuple(result.keys()) == ("debug", "missing", "levels", "r")
    assert type(host.names["config"]) is FrozenMap


def test_host_constant_holds_host_values() -> None:
    host = make_host(
        names={"pkg": Package("a", "1")},
        types={Package: frozenset({"name", "version"})},
    )
    assert evaluate_source("n = pkg.name", host=host)["n"] == "a"


def test_file_may_shadow_a_host_constant() -> None:
    host = make_host(names={"config": {}})
    assert evaluate_source("config = 1", host=host)["config"] == 1


@pytest.mark.parametrize(
    "value",
    [
        FrozenMap({"f": Builtin("f", len)}),
        (object(),),
        frozenset({Package("a", "1")}),
        FrozenMap({Package("a", "1"): 1}),
    ],
)
def test_host_constant_must_be_a_value(value: object) -> None:
    with pytest.raises(TypeError):
        Host(FrozenMap({"x": value}), FrozenMap())


def test_make_host_refuses_mutable_unknown_constant() -> None:
    with pytest.raises(TypeError):
        make_host(names={"x": object()})


def _names(values: FrozenMap) -> dict[str, object]:
    return {str(k): v for k, v in values.items()}


LAYER = """
SUFFIX = "!"

def shout(text):
    return text.upper() + SUFFIX

def broken(x):
    return x["missing"]

def spin(n):
    return [i for i in range(n)]
"""


def test_functions_pass_between_layers() -> None:
    first = evaluate_source(LAYER, "first.pyb")
    host = make_host({str(k): v for k, v in first.items() if k != "SUFFIX"})
    second = evaluate_source(
        "loud = shout('hi')\nlate = (lambda: shout)()\nboth = [shout, late]",
        "second.pyb",
        host=host,
    )
    assert second["loud"] == "HI!"
    assert second["late"] is first["shout"]
    with pytest.raises(EvaluationError, match="name 'SUFFIX' is not defined"):
        evaluate_source("x = SUFFIX", "second.pyb", host=host)


def test_errors_in_a_shared_function_name_its_file() -> None:
    host = make_host(_names(evaluate_source(LAYER, "first.pyb")))
    with pytest.raises(EvaluationError) as caught:
        evaluate_source("\n\nx = broken({})", "second.pyb", host=host)
    assert caught.value.filename == "first.pyb"
    assert caught.value.lineno == 8
    with pytest.raises(EvaluationError) as caught:
        evaluate_source("x = shout()\ny = undefined", "second.pyb", host=host)
    assert caught.value.filename == "second.pyb"
    with pytest.raises(EvaluationError) as caught:
        evaluate_source("x = shout('a')\ny = undefined", "second.pyb", host=host)
    assert (caught.value.filename, caught.value.lineno) == ("second.pyb", 2)
    with pytest.raises(LimitExceeded) as limit:
        evaluate_source(
            "x = spin(50)", "second.pyb", host=host, limits=Limits(max_collection_len=10)
        )
    assert limit.value.filename == "first.pyb"


def test_a_shared_function_cannot_recurse_through_a_later_file() -> None:
    first = evaluate_source("def apply(f, x):\n    return f(x)\n", "first.pyb")
    host = make_host(_names(first))
    with pytest.raises(EvaluationError, match="recursion into apply"):
        evaluate_source(
            "def again(x):\n    return apply(again, x)\ny = apply(again, 1)",
            "second.pyb",
            host=host,
        )
