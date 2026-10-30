# Changelog

All notable changes to PyBonsai are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-10-31

### Added

- A host name may hold a function defined by an earlier evaluation, so a
  program can evaluate files in layers where each layer calls the
  functions of the layers before it. The function runs in the scope it
  was defined in, and an error or limit inside it names the file and line
  that define it. Recursion through another file is still refused.

## [1.1.0] - 2026-10-30

### Added

- A host name may hold a constant as well as a `Builtin`: a string,
  number, bool, None, or a list, set or dict of such values and host type
  instances. `make_host` freezes it, so a file reads a dict given here as
  a read-only mapping. Lattice uses this to give a system description the
  options chosen with Trellis as `config`.

## [1.0.0] - 2026-10-29

First release, published on PyPI as `pybonsai-lang`.

### Added

- Parser for the Python 3.12 grammar, and a checker that refuses every
  construct outside the allow list of RFC 0001 section 7 before anything
  is evaluated, including imports, `while`, recursion, mutation, dunder
  access and I/O.
- An evaluator that interprets the checked syntax tree, with immutable
  values: lists, dicts and sets become tuples, mappings and frozensets.
- Fixed limits on size, nesting depth and evaluation steps, so every
  evaluation finishes.
- The prelude of pure built-in functions.
- `Host`, `make_host` and `Builtin`, through which a program adds its own
  functions and immutable value types.
- Errors with the file and line of the construct involved.

### Stability

The language, the `pybonsai` names in `__all__` and the error types are
the public interface. Any change that makes a valid file invalid, or
gives it a different result, needs a new major version.
