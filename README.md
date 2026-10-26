# PyBonsai

PyBonsai is a restricted subset of Python 3.12 for writing configuration
that must give the same result on every machine. It is the configuration
language of [PyrixOS](https://github.com/PacketFive/PyrixOS) and is defined
in section 7 of RFC 0001, but the package has no knowledge of packages or
builds and can be embedded in any Python program.

A PyBonsai file is ordinary Python syntax. It is never run by CPython.
PyBonsai parses it into a syntax tree, rejects every construct outside an
allow list, and then interprets the tree itself. A file therefore cannot:

* read or write files, open network connections, or read the clock or
  environment variables;
* change a value after creating it, since lists, dicts and sets become
  immutable tuples, mappings and frozensets;
* loop without a bound, since `while` and recursion are rejected and every
  `for` runs over a finite collection.

The same file with the same inputs always produces the same values, and
evaluation always finishes within fixed limits.

## Status

Implemented. The parser, checker and evaluator follow RFC 0001 section 7,
and the tests encode its rules. The coverage floor is 80%.

## Install

```sh
pip install --config-settings editable_mode=strict -e '.[dev]'
pybootstrap check
```

Python 3.12 or later is required. There are no runtime dependencies. The
`dev` extra installs [pybootstrap](https://github.com/packetfive/pybootstrap)
and the tools its gates drive: ruff for formatting and lint, pyright for
type checking, pytest with coverage (at least 80%), and hypothesis for
property tests. Each tool also works on its own, for example `pytest` or
`ruff check src tests`.

The repository's `src` directory is the package itself, mapped to its
import name in `pyproject.toml`. Strict editable mode gives that mapping a
real `pybonsai/` directory under `build/`, which pyright needs to find the
package. Tests import the installed package, so install before running
them.

## Use

```python
from pybonsai import evaluate_source

names = evaluate_source("xs = [i * i for i in range(4)]")
assert names["xs"] == (0, 1, 4, 9)
```

A program adds its own functions and value types through a `Host`:

```python
from pybonsai import Builtin, evaluate_source, make_host

host = make_host(
    names={"double": Builtin("double", lambda x: 2 * x)},
    types={},
)
evaluate_source("y = double(21)", host=host)
```

Host types must be immutable and hashable, and each one lists the
attributes a file may read. Without a host, a file sees only the prelude:
`len`, `range`, `sorted`, `min`, `max`, `sum`, `any`, `all`, `abs`, `str`,
`int`, `bool`, `enumerate`, `zip` and `reversed`.

## Layout

| Module | Role |
| --- | --- |
| `parser.py` | Parse source with the Python 3.12 grammar |
| `checker.py` | Reject constructs outside the allow list before evaluation |
| `allowlist.py` | Permitted syntax nodes, operators and attributes |
| `evaluator.py` | Interpret the checked syntax tree |
| `values.py` | Immutable value types, freezing and attribute access |
| `scope.py` | Name lookup for module and function scopes |
| `limits.py` | Size, depth and step limits |
| `prelude.py` | The pure built-in functions |
| `host.py` | The interface for embedding programs |
| `errors.py` | Error types with file and line positions |

## License

GPL-2.0-only.
