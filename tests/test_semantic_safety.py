"""Regression tests for semantic bugs the syntax guard cannot catch.

The bot's transform_all only checks that rewritten code still parses. That
misses changes which parse fine but alter behaviour, which is how
fix_mutable_defaults and remove_unused_imports shipped broken.

Each test here asserts behaviour, not syntax.
"""
import ast
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import improve  # noqa: E402


@pytest.fixture()
def transformer():
    return improve.CodeTransformer()


def run(src, fn_name):
    ns = {}
    exec(src, ns)
    return ns[fn_name]


# --------------------------------------------------------------------------
# Mutable defaults must keep the value the author wrote. The old rewrite
# substituted an empty container, so f(x=[1,2]) silently went from [1,2] to [].
# --------------------------------------------------------------------------
def test_mutable_default_list_keeps_contents(transformer):
    out = transformer.fix_mutable_defaults("def f(x=[1, 2]):\n    return x\n")
    assert out is not None
    assert run(out, "f")() == [1, 2]


def test_mutable_default_empty_list_is_fresh_per_call(transformer):
    out = transformer.fix_mutable_defaults("def f(x=[]):\n    x.append(1)\n    return x\n")
    f = run(out, "f")
    assert f() == [1]
    assert f() == [1], "default must not be shared between calls"


def test_mutable_default_set_stays_a_set(transformer):
    out = transformer.fix_mutable_defaults("def f(s={1, 2}):\n    return s\n")
    assert run(out, "f")() == {1, 2}


def test_mutable_default_dict_keeps_contents(transformer):
    out = transformer.fix_mutable_defaults("def f(d={'a': 1}):\n    return d\n")
    assert run(out, "f")() == {"a": 1}


# --------------------------------------------------------------------------
# Unused-import pruning must not delete names that are genuinely needed.
# --------------------------------------------------------------------------
def test_keeps_import_reexported_via_all(transformer):
    src = 'import os\n__all__ = ["os"]\n'
    out = transformer.remove_unused_imports(src)
    assert "import os" in (out if out is not None else src)


def test_keeps_import_used_only_in_string_annotation(transformer):
    src = 'import typing\ndef f(x: "typing.List[int]"):\n    return x\n'
    out = transformer.remove_unused_imports(src)
    assert "import typing" in (out if out is not None else src)


def test_keeps_import_used_only_via_eval(transformer):
    src = 'import math\ndef f():\n    return eval("math.pi")\n'
    out = transformer.remove_unused_imports(src)
    assert "import math" in (out if out is not None else src)


def test_partial_from_import_keeps_used_name(transformer):
    src = "from os.path import join, exists\ndef f():\n    return join('a', 'b')\n"
    out = transformer.remove_unused_imports(src)
    assert out is not None
    assert "join" in out
    assert "exists" not in out


def test_still_removes_a_truly_unused_import(transformer):
    src = "import os\ndef f():\n    return 1\n"
    out = transformer.remove_unused_imports(src)
    assert out is not None and "import os" not in out


# --------------------------------------------------------------------------
# A module docstring has to be the first statement or it is not a docstring.
# Inserting it after "from __future__" left module __doc__ as None.
# --------------------------------------------------------------------------
def test_module_docstring_is_set_with_future_import(transformer):
    out = transformer.add_module_docstring(
        "from __future__ import annotations\n\ndef f():\n    return 1\n"
    )
    assert run(out, "f") is not None
    ns = {}
    exec(out, ns)
    assert ns["__doc__"] is not None


def test_module_docstring_keeps_shebang_first(transformer):
    out = transformer.add_module_docstring("#! /usr/bin/env python\nimport os\n")
    assert out.split("\n")[0].startswith("#!")


# --------------------------------------------------------------------------
# Licence claims must match the repository. docutrust is Apache-2.0, so an MIT
# badge or an "licensed under the MIT License" section is simply false.
# --------------------------------------------------------------------------
def test_no_mit_claim_for_apache_repo():
    out = improve.improve_readme("# T\n\nBody\n", {"license": {"spdx_id": "Apache-2.0"}}, ["a.py"])
    assert "MIT" not in out


def test_no_licence_section_when_unknown():
    out = improve.improve_readme("# T\n\nBody\n", {"license": None}, ["a.py"])
    assert "## License" not in out


def test_mit_repo_gets_licence_section():
    out = improve.improve_readme("# T\n\nBody\n", {"license": {"spdx_id": "MIT"}}, ["a.py"])
    assert "## License" in out


def test_python_badge_matches_project_requirement():
    out = improve.improve_readme("# T\n\nBody\n", {"license": {"spdx_id": "MIT"}}, ["a.py"])
    assert "3.10+" in out
    assert "3.8+" not in out


# --------------------------------------------------------------------------
# Topics must not be one hardcoded set applied to every repository.
# --------------------------------------------------------------------------
def test_topics_are_domain_derived_not_hardcoded():
    src = Path(improve.__file__).read_text(encoding="utf-8")
    assert '"high-precision"]' not in src
    assert "by_domain" in src


def test_no_dead_has_readme_variable():
    src = Path(improve.__file__).read_text(encoding="utf-8")
    assert "has_readme" not in src


# --------------------------------------------------------------------------
# End to end: the whole pipeline must preserve behaviour, not just syntax.
# --------------------------------------------------------------------------
def test_pipeline_preserves_behaviour_and_parses():
    src = textwrap.dedent(
        """
        import sys
        __all__ = ["sys"]

        def parse(values=[1, 2]):
            values.append(3)
            return values
        """
    )
    fixed, _ = improve.improve_python_file(src, "demo.py")
    assert fixed is not None
    ast.parse(fixed)
    before, after = {}, {}
    exec(src, before)
    exec(fixed, after)
    assert after["parse"]() == before["parse"]()
    assert "sys" in after, "re-exported module was dropped"
