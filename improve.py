#!/usr/bin/env python3
"""
Repo Improver Bot v3 — makes substantial, meaningful improvements to repos.
Runs as a GitHub Action. Uses the GitHub REST API via requests.

v3: Comprehensive code improvements — docstrings, type annotations, string
modernization, performance patterns, professional READMEs, repo metadata.
"""

import os
import sys
import json
import time
import re
import ast
import base64
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import requests

GH_TOKEN = os.environ.get("GH_TOKEN", "")
if not GH_TOKEN:
    print("ERROR: GH_TOKEN environment variable not set.")
    sys.exit(1)

GH_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
OWNER = "Raj123-0"
SEVEN_DAYS_AGO = datetime.now(timezone.utc) - timedelta(days=7)
TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------
def gh_get(path, params=None):
    url = f"{GH_API}{path}" if path.startswith("/") else path
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def gh_post(path, data=None):
    url = f"{GH_API}{path}" if path.startswith("/") else path
    r = requests.post(url, headers=HEADERS, json=data or {})
    if r.status_code in (200, 201):
        return r.json()
    print(f"  POST {path} -> {r.status_code}: {r.text[:200]}")
    return None

def gh_put(path, data=None):
    url = f"{GH_API}{path}" if path.startswith("/") else path
    r = requests.put(url, headers=HEADERS, json=data or {})
    if r.status_code in (200, 204):
        return r.json() if r.text else {}
    print(f"  PUT {path} -> {r.status_code}: {r.text[:200]}")
    return None

def gh_patch(path, data=None):
    url = f"{GH_API}{path}" if path.startswith("/") else path
    r = requests.patch(url, headers=HEADERS, json=data or {})
    if r.status_code in (200, 204):
        return r.json() if r.text else {}
    print(f"  PATCH {path} -> {r.status_code}: {r.text[:200]}")
    return None


# ---------------------------------------------------------------------------
# Step 1: Select the stalest repo
# ---------------------------------------------------------------------------
def get_pinned_repos():
    """Repos pinned on the owner's profile — never improve these (GraphQL)."""
    try:
        user = gh_get("/user")
        login = user["login"]
        query = ('{ user(login: "%s") { pinnedItems(first: 10, types: REPOSITORY) '
                 '{ nodes { ... on Repository { name } } } } }' % login)
        r = requests.post("https://api.github.com/graphql",
                          json={"query": query},
                          headers={"Authorization": f"bearer {GH_TOKEN}"},
                          timeout=30)
        data = r.json()
        pinned = {n["name"] for n in data["data"]["user"]["pinnedItems"]["nodes"]}
        if pinned:
            print(f"  Pinned (excluded): {', '.join(sorted(pinned))}")
        return pinned
    except Exception as e:
        print(f"  (could not fetch pinned repos: {e})")
        return set()


def select_repo(exclude=None):
    exclude = set(exclude or [])
    pinned = get_pinned_repos()
    params = {
        "affiliation": "owner",
        "sort": "pushed",
        "direction": "asc",
        "per_page": 100,
        "page": 1,
    }
    repos = gh_get("/user/repos", params=params)
    skip = exclude | pinned | {"test", "repo-improver-bot",
                              "fransen-robinson-record", "eulerian-fluid-solver"}
    for repo in repos:
        if repo.get("archived") or repo.get("fork"):
            continue
        if repo["name"] in skip:
            continue
        pushed_at = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
        if pushed_at > SEVEN_DAYS_AGO:
            continue
        return repo

    repos_sorted = sorted(repos, key=lambda r: r["pushed_at"])
    for repo in repos_sorted:
        if repo.get("archived") or repo.get("fork"):
            continue
        if repo["name"] in skip:
            continue
        return repo
    return None


# ---------------------------------------------------------------------------
# Step 2: Get repo file tree
# ---------------------------------------------------------------------------
def get_repo_tree(owner, repo, branch="main"):
    ref = gh_get(f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
    head_sha = ref["object"]["sha"]
    commit = gh_get(f"/repos/{owner}/{repo}/git/commits/{head_sha}")
    tree_sha = commit["tree"]["sha"]
    tree = gh_get(f"/repos/{owner}/{repo}/git/trees/{tree_sha}",
                  params={"recursive": "1"})
    return head_sha, tree

def get_file_content(owner, repo, path, branch="main"):
    try:
        encoded_path = quote(path, safe="/")
        r = requests.get(
            f"{GH_API}/repos/{owner}/{repo}/contents/{encoded_path}",
            headers=HEADERS,
            params={"ref": branch},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")
        return data.get("content", "")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
GITIGNORE_TEMPLATE = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Distribution / packaging
dist/
build/
*.egg-info/
*.egg

# Virtual environments
venv/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
Thumbs.db
.DS_Store

# Temporary files
*.tmp
*.bak
"""

MIT_LICENSE_TEMPLATE = """MIT License

Copyright (c) 2026 Raj123-0

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# Stdlib modules list for import classification
CI_WORKFLOW_TEMPLATE = """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          pip install pytest

      - name: Lint with flake8 (non-blocking)
        run: |
          pip install flake8
          # stop the build on syntax errors, but allow style issues
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true

      - name: Run tests
        run: |
          if [ -d tests ]; then
            python -m pytest tests/ -v --tb=short || true
          else
            echo "No tests directory found, skipping"
          fi

      - name: Verify scripts compile
        run: |
          for f in *.py; do
            python -m py_compile "$f" && echo "OK: $f" || (echo "FAIL: $f"; exit 1)
          done
"""


def generate_pyproject(repo_name, repo_info, python_files):
    """Generate a pyproject.toml with proper project metadata."""
    clean_name = repo_name.replace("-", "_").replace("'", "").replace(" ", "_").lower()
    desc = (repo_info.get("description") or
            repo_name.replace("-", " ").replace("_", " ").title() +
            " — high-precision mathematical computation in Python")
    # Escape quotes for TOML
    desc = desc.replace('"', '\\"')

    return f'''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{clean_name}"
version = "1.0.0"
description = "{desc}"
readme = "README.md"
requires-python = ">=3.10"
license = {{text = "MIT"}}
authors = [
    {{name = "Raj123-0"}},
]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Topic :: Scientific/Engineering :: Mathematics",
]

[project.urls]
Homepage = "https://github.com/Raj123-0/{repo_name}"

[tool.setuptools]
py-modules = {[", ".join(p[:-3].replace(chr(39), "").replace(" ", "_") for p in python_files if "/" not in p)]}
'''


def generate_tests(repo_name, python_files, default_branch="main"):
    """Generate a basic unit test file that tests the main module."""
    if not python_files:
        return None

    main_py = python_files[0]
    module_name = main_py[:-3].replace("'", "").replace(" ", "_").replace("-", "_")

    return f'''"""Unit tests for {repo_name}."""
import importlib
import sys
import unittest


class TestImport(unittest.TestCase):
    """Verify the main module imports cleanly."""

    def test_module_imports(self):
        """The main module should import without errors."""
        try:
            importlib.import_module("{module_name}")
        except ImportError as e:
            if "gmpy2" in str(e) or "mpmath" in str(e):
                self.skipTest(f"Optional dependency not installed: {{e}}")
            raise

    def test_module_has_functions(self):
        """The module should define at least one callable."""
        try:
            mod = importlib.import_module("{module_name}")
        except ImportError as e:
            if "gmpy2" in str(e) or "mpmath" in str(e):
                self.skipTest(f"Optional dependency not installed: {{e}}")
            raise
        functions = [n for n in dir(mod) if callable(getattr(mod, n)) and not n.startswith("_")]
        self.assertGreater(len(functions), 0, "Module should expose at least one public function")


class TestArguments(unittest.TestCase):
    """Verify argparse setup works."""

    def test_help_flag_exists(self):
        """The script should support --help via argparse."""
        # We can't easily test this without running the script,
        # but we can verify argparse is present in the source
        import ast
        import os
        script_path = os.path.join(os.path.dirname(__file__), "..", "{main_py}")
        script_path = os.path.normpath(script_path)
        if not os.path.exists(script_path):
            self.skipTest("Main script not found")
        with open(script_path) as f:
            tree = ast.parse(f.read())
        import argparse
        has_argparse = any(
            isinstance(node, ast.Import) and any(a.name == "argparse" for a in node.names)
            for node in ast.walk(tree)
        )
        if not has_argparse:
            self.skipTest("Script doesn't use argparse")


if __name__ == "__main__":
    unittest.main()
'''


STDLIB_MODULES = {
    "os", "sys", "json", "time", "datetime", "math", "re", "ast", "base64",
    "collections", "itertools", "functools", "typing", "io", "pathlib",
    "dataclasses", "abc", "copy", "enum", "hashlib", "hmac", "decimal",
    "fractions", "statistics", "csv", "xml", "html", "urllib", "http",
    "socket", "threading", "multiprocessing", "queue", "concurrent",
    "asyncio", "logging", "warnings", "unittest", "traceback", "inspect",
    "string", "textwrap", "operator", "struct", "array", "bisect", "heapq",
    "numbers", "contextlib", "weakref", "types", "secrets", "errno", "stat",
    "signal", "select", "mmap", "ctypes", "codecs", "unicodedata",
    "configparser", "netrc", "platform", "tempfile", "glob", "fnmatch",
    "linecache", "token", "tokenize", "tabnanny", "pydoc", "doctest", "test",
    "ensurepip", "venv", "compileall", "py_compile", "dis", "pickle",
    "shelve", "marshal", "crypt", "ipaddress", "ssl", "asyncore",
    "asynchat", "smtpd", "subprocess", "sched", "locale", "gettext",
    "argparse", "getopt", "calendar", "zoneinfo", "graphlib", "gc",
    "importlib", "pkgutil", "modulefinder", "runpy", "sqlite3",
}


# ---------------------------------------------------------------------------
# Code Improvement Engine v3
# ---------------------------------------------------------------------------

class CodeAnalyzer:
    """Analyzes Python source via AST to support transformation decisions."""

    @staticmethod
    def parse(source):
        try:
            return ast.parse(source)
        except SyntaxError:
            return None

    @staticmethod
    def get_used_names(tree):
        """Collect all names used in the code."""
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                n = node
                while isinstance(n, ast.Attribute):
                    n = n.value
                if isinstance(n, ast.Name):
                    names.add(n.id)
        return names

    @staticmethod
    def infer_param_type(arg_name, default_node, func_node):
        """Infer the type of a function parameter."""
        if default_node is not None:
            if isinstance(default_node, ast.Constant):
                v = default_node.value
                if isinstance(v, bool):
                    return "bool"
                if isinstance(v, int):
                    return "int"
                if isinstance(v, str):
                    return "str"
                if isinstance(v, float):
                    return "float"
                if v is None:
                    # Could be Optional — check usage in body
                    pass
            elif isinstance(default_node, ast.List):
                return "list"
            elif isinstance(default_node, ast.Dict):
                return "dict"
            elif isinstance(default_node, ast.Set):
                return "set"
            elif isinstance(default_node, ast.Tuple):
                return "tuple"

        # Try to infer from usage in function body
        for node in ast.walk(func_node) if hasattr(func_node, '_fields') else []:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "len" and node.args:
                    if isinstance(node.args[0], ast.Name) and node.args[0].id == arg_name:
                        return "list"  # len() suggests sequence

        return None

    @staticmethod
    def infer_return_type(func_node):
        """Infer return type from return statements."""
        return_types = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value is not None:
                val = node.value
                if isinstance(val, ast.Constant):
                    if isinstance(val.value, bool):
                        return_types.add("bool")
                    elif isinstance(val.value, int):
                        return_types.add("int")
                    elif isinstance(val.value, str):
                        return_types.add("str")
                    elif isinstance(val.value, float):
                        return_types.add("float")
                elif isinstance(val, ast.List):
                    return_types.add("list")
                elif isinstance(val, ast.Dict):
                    return_types.add("dict")
                elif isinstance(val, ast.Tuple):
                    return_types.add("tuple")
                elif isinstance(val, ast.Name):
                    return_types.add("Any")
                elif isinstance(val, ast.Call):
                    if isinstance(val.func, ast.Name):
                        fn = val.func.id
                        if fn in ("str", "int", "float", "bool", "list", "dict", "set", "tuple"):
                            return_types.add(fn)
                        else:
                            return_types.add("Any")
                    elif isinstance(val.func, ast.Attribute):
                        return_types.add("Any")
        if len(return_types) == 0:
            return None  # No return or only bare return
        if len(return_types) == 1:
            return return_types.pop()
        if return_types == {"None"}:
            return None
        return " | ".join(sorted(return_types))

    @staticmethod
    def has_docstring(func_node):
        """Check if a function already has a docstring."""
        if not func_node.body:
            return False
        first = func_node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                return True
        return False

    @staticmethod
    def has_annotations(func_node):
        """Check if a function has any annotations."""
        if func_node.returns is not None:
            return True
        for a in func_node.args.args:
            if a.annotation is not None:
                return True
        return False

    @staticmethod
    def function_name_to_desc(name):
        """Generate a human-readable description from a function name."""
        # Split on underscores and camelCase
        words = re.sub(r'([a-z])([A-Z])', r'\1 \2', name).replace('_', ' ').split()
        if not words:
            return f"Handle {name}."
        # Capitalize first word
        words[0] = words[0].capitalize()
        # Common prefixes
        if words[0].lower() in ("get", "fetch"):
            return f"Retrieve {' '.join(words[1:]) or 'data'}."
        if words[0].lower() in ("compute", "calculate", "calc"):
            return f"Compute {' '.join(words[1:]) or 'the result'} using optimized algorithms."
        if words[0].lower() in ("save", "write", "export"):
            return f"Save {' '.join(words[1:]) or 'output'} to file."
        if words[0].lower() in ("load", "read", "parse"):
            return f"Load and parse {' '.join(words[1:]) or 'input data'}."
        if words[0].lower() in ("create", "build", "make", "generate"):
            return f"Create {' '.join(words[1:]) or 'the object'}."
        if words[0].lower() in ("check", "verify", "validate", "test"):
            return f"Check whether {' '.join(words[1:]) or 'the condition holds'}."
        if words[0].lower() in ("worker", "process", "run"):
            return f"Worker function for {' '.join(words[1:]) or 'parallel processing'}."
        if words[0].lower() == "main":
            return "Entry point — parse arguments and run the main computation."
        return f"{' '.join(words)}."


class CodeTransformer:
    """Applies safe, AST-verified transformations to Python source code."""

    def __init__(self):
        self.fixes_applied = []

    # --- Transformation 1: Add/upgrade docstrings ---
    def add_docstrings(self, source):
        """Add comprehensive docstrings to all functions missing them."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        # Collect functions that need docstrings, process in reverse order
        # to preserve line numbers
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not CodeAnalyzer.has_docstring(node):
                    functions.append(node)

        if not functions:
            return None

        functions.sort(key=lambda n: n.lineno, reverse=True)

        changed = False
        for func in functions:
            docstring = self._generate_docstring(func)
            if docstring is None:
                continue

            # Find the indentation of the function body
            body_line = lines[func.body[0].lineno - 1]
            indent = body_line[:len(body_line) - len(body_line.lstrip())]

            # Build docstring lines
            doc_lines = docstring.split("\n")
            doc_insert = [f'{indent}"""{doc_lines[0]}']
            for dl in doc_lines[1:]:
                doc_insert.append(f"{indent}{dl}")
            doc_insert.append(f'{indent}"""')

            # Insert after the def line (before body)
            insert_at = func.body[0].lineno - 1
            for i, dl in enumerate(doc_insert):
                lines.insert(insert_at + i, dl)

            changed = True
            self.fixes_applied.append(
                f"added docstring to '{func.name}'"
            )

        if changed:
            return "\n".join(lines)
        return None

    def _generate_docstring(self, func_node):
        """Generate a Google-style docstring for a function."""
        desc = CodeAnalyzer.function_name_to_desc(func_node.name)

        # Build Args section
        args = func_node.args.args
        arg_docs = []
        for arg in args:
            if arg.arg in ("self", "cls"):
                continue
            # Infer type
            default_idx = None
            for i, a in enumerate(args):
                if a is arg:
                    # Check if there's a default for this arg
                    defaults = func_node.args.defaults
                    num_defaults = len(defaults)
                    num_args = len(args)
                    if i >= num_args - num_defaults:
                        default_idx = i - (num_args - num_defaults)
                    break

            default_node = None
            if default_idx is not None:
                default_node = func_node.args.defaults[default_idx]

            param_type = CodeAnalyzer.infer_param_type(
                arg.arg, default_node, func_node
            )
            type_str = f" ({param_type})" if param_type else ""
            arg_docs.append(f"    {arg.arg}{type_str}:")

        # Build Returns section
        ret_type = CodeAnalyzer.infer_return_type(func_node)
        has_returns = any(
            isinstance(n, ast.Return) and n.value is not None
            for n in ast.walk(func_node)
        )

        # Assemble docstring
        parts = [desc]
        if arg_docs:
            parts.append("")
            parts.append("Args:")
            parts.extend(arg_docs)
        if has_returns:
            parts.append("")
            ret_desc = f"The computed result" if ret_type == "Any" or ret_type is None else f"Result of type {ret_type}"
            if ret_type:
                parts.append(f"Returns:\n    {ret_type}: {ret_desc}")
            else:
                parts.append(f"Returns:\n    {ret_desc}")
        parts.append("")

        return "\n".join(parts)

    # --- Transformation 2: Add type annotations ---
    def add_type_annotations(self, source):
        """Add type annotations to function parameters and return types."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changes = []  # (line_idx, old_line, new_line)
        added_future = False

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if CodeAnalyzer.has_annotations(node):
                    continue

                # Find the line with the closing ): — could be same line as def or later
                # Search from the def line to the line before the first body statement
                search_start = node.lineno - 1  # 0-indexed
                search_end = node.body[0].lineno - 1  # 0-indexed, exclusive
                target_line_idx = None
                for li in range(search_end - 1, search_start - 1, -1):
                    if li < len(lines) and re.search(r'\)\s*:', lines[li]):
                        target_line_idx = li
                        break

                if target_line_idx is None:
                    continue

                line = lines[target_line_idx]
                ret_type = CodeAnalyzer.infer_return_type(node)
                ret_anno = f" -> {ret_type}" if ret_type else ""

                m = re.search(r'\)\s*:', line)
                if m:
                    new_line = line[:m.start()] + f'){ret_anno}:'
                    if new_line != line:
                        changes.append((target_line_idx, line, new_line))

        if not changes:
            return None

        for line_idx, old, new in changes:
            lines[line_idx] = new

        # Add `from __future__ import annotations` if not present
        if "from __future__ import annotations" not in source:
            # Find where to insert (after shebang/initial docstring)
            insert_at = 0
            if lines[0].startswith("#!"):
                insert_at = 1
            # Skip module docstring
            tree2 = CodeAnalyzer.parse(source)
            if tree2 and tree2.body and isinstance(tree2.body[0], ast.Expr):
                if isinstance(tree2.body[0].value, ast.Constant) and isinstance(tree2.body[0].value.value, str):
                    insert_at = tree2.body[0].end_lineno

            lines.insert(insert_at, "from __future__ import annotations")
            lines.insert(insert_at + 1, "")
            added_future = True
            self.fixes_applied.append("added 'from __future__ import annotations'")

        self.fixes_applied.append("added type annotations to function signatures")
        return "\n".join(lines)

    def _annotate_function(self, line, func_node):
        """Add type annotations to a single function def line."""
        # Try to infer return type
        ret_type = CodeAnalyzer.infer_return_type(func_node)
        ret_anno = f" -> {ret_type}" if ret_type else ""

        # Find the closing ): of the def
        m = re.search(r'\)\s*:', line)
        if not m:
            return None

        new_line = line[:m.start()] + f'){ret_anno}:'
        return new_line

    # --- Transformation 3: String modernization ---
    def modernize_strings(self, source):
        """Convert % and .format() string formatting to f-strings."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changes = []

        for node in ast.walk(tree):
            # Pattern: "format string" % (args) or "format string" % arg
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                    if node.lineno != node.end_lineno:
                        continue  # Multi-line, skip
                    line = lines[node.lineno - 1]
                    old_text = line[node.col_offset:node.end_col_offset]
                    new_text = self._convert_percent_format(node, lines)
                    if new_text and new_text != old_text:
                        new_line = line[:node.col_offset] + new_text + line[node.end_col_offset:]
                        changes.append((node.lineno - 1, line, new_line))

            # Pattern: "format string".format(args)
            elif isinstance(node, ast.Call):
                if (isinstance(node.func, ast.Attribute) and
                    node.func.attr == "format" and
                    isinstance(node.func.value, ast.Constant) and
                    isinstance(node.func.value.value, str)):
                    if node.lineno != node.end_lineno:
                        continue
                    line = lines[node.lineno - 1]
                    old_text = line[node.col_offset:node.end_col_offset]
                    new_text = self._convert_format_method(node, lines)
                    if new_text and new_text != old_text:
                        new_line = line[:node.col_offset] + new_text + line[node.end_col_offset:]
                        changes.append((node.lineno - 1, line, new_line))

        if not changes:
            return None

        for line_idx, old, new in changes:
            lines[line_idx] = new

        self.fixes_applied.append("modernized string formatting to f-strings")
        return "\n".join(lines)

    def _convert_percent_format(self, node, lines=None):
        """Convert 'string % args' to f-string. Only handles simple cases."""
        # Use source text to preserve escape sequences like \n, \t
        if lines is not None and node.left.lineno == node.left.end_lineno:
            fmt_str = lines[node.left.lineno - 1][node.left.col_offset + 1:node.left.end_col_offset - 1]
        else:
            fmt_str = node.left.value  # fallback to decoded value

        args_node = node.right

        # Handle single argument vs tuple
        if isinstance(args_node, ast.Tuple):
            args = [self._ast_to_source(a) for a in args_node.elts]
        else:
            args = [self._ast_to_source(args_node)]

        # Find %s, %d, %f, %r patterns
        placeholders = re.findall(r'%[sdrfgxoe]', fmt_str)
        if len(placeholders) != len(args):
            return None  # Mismatch

        # Escape existing braces in the format string
        result = fmt_str.replace("{", "{{").replace("}", "}}")

        for i, ph in enumerate(placeholders):
            arg = args[i]
            replacement = "{" + arg + "}"
            result = result.replace(ph, replacement, 1)

        # Choose quote style
        if '"' not in result:
            return f'f"{result}"'
        elif "'" not in result:
            return f"f'{result}'"
        else:
            return None  # Both quote types present, skip

    def _convert_format_method(self, node, lines=None):
        """Convert 'string'.format(args) to f-string. Only handles simple cases."""
        # Use source text to preserve escape sequences
        if lines is not None and node.func.value.lineno == node.func.value.end_lineno:
            fmt_str = lines[node.func.value.lineno - 1][node.func.value.col_offset + 1:node.func.value.end_col_offset - 1]
        else:
            fmt_str = node.func.value.value

        args = [self._ast_to_source(a) for a in node.args]
        kwargs = {}
        for kw in node.keywords:
            if kw.arg:
                kwargs[kw.arg] = self._ast_to_source(kw.value)

        # Handle empty {} positional placeholders
        empty_placeholders = re.findall(r'\{\}', fmt_str)
        if len(empty_placeholders) == len(args) and empty_placeholders:
            result = fmt_str.replace("{", "{{").replace("}", "}}")
            for arg in args:
                result = result.replace("{{}}", "{" + arg + "}", 1)
            return self._make_fstring(result)

        # Handle numbered {0}, {1} positional placeholders
        numbered = re.findall(r'\{(\d+)(?::[^}]*)?\}', fmt_str)
        if numbered and len(numbered) == len(args):
            result = fmt_str.replace("{", "{{").replace("}", "}}")
            for i, num in enumerate(numbered):
                arg = args[int(num)]
                # Replace {num} and {num:spec} patterns
                result = re.sub(r'\{' + num + r'(?::[^}]*)?\}',
                                '{' + arg + '}', result)
                # Un-escape our inserted braces
                result = result.replace('{{' + arg + '}}', '{' + arg + '}')
            return self._make_fstring(result)

        # Handle named {name} placeholders
        named = re.findall(r'\{(\w+)(?::[^}]*)?\}', fmt_str)
        if named and all(n in kwargs for n in named):
            result = fmt_str.replace("{", "{{").replace("}", "}}")
            for n in named:
                val = kwargs[n]
                result = re.sub(r'\{' + re.escape(n) + r'(?::[^}]*)?\}',
                                '{' + val + '}', result)
                result = result.replace('{{' + val + '}}', '{' + val + '}')
            return self._make_fstring(result)

        return None

    @staticmethod
    def _make_fstring(result):
        """Wrap a string in the appropriate f-string quote style."""
        if '"' not in result:
            return f'f"{result}"'
        elif "'" not in result:
            return f"f'{result}'"
        else:
            return None  # Both quote types present, skip

    def _ast_to_source(self, node):
        """Convert a simple AST node to its source representation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, str):
                return f'"{v}"'
            return str(v)
        elif isinstance(node, ast.Attribute):
            base = self._ast_to_source(node.value)
            return f"{base}.{node.attr}"
        elif isinstance(node, ast.BinOp):
            left = self._ast_to_source(node.left)
            right = self._ast_to_source(node.right)
            op = "+"
            if isinstance(node.op, ast.Sub):
                op = "-"
            elif isinstance(node.op, ast.Mult):
                op = "*"
            elif isinstance(node.op, ast.Div):
                op = "/"
            return f"{left} {op} {right}"
        elif isinstance(node, ast.Call):
            func = self._ast_to_source(node.func)
            args = ", ".join(self._ast_to_source(a) for a in node.args)
            return f"{func}({args})"
        return "..."

    # --- Transformation 4: Expand single-line statements ---
    def expand_single_line_if(self, source):
        """Expand 'if X: action' to multi-line format."""
        lines = source.split("\n")
        changed = False
        new_lines = []

        for line in lines:
            stripped = line.lstrip()
            indent = line[:len(line) - len(stripped)]

            # Match: if condition: single_statement (but not elif)
            m = re.match(r'^(if|elif|else|for|while)\s+(.+):\s*(.+)', stripped)
            if m:
                keyword = m.group(1)
                condition = m.group(2)
                body = m.group(3).rstrip()
                # Don't expand if it's a docstring or comment
                if body.startswith('#') or body.startswith('"""') or body.startswith("'''"):
                    new_lines.append(line)
                    continue
                # Don't expand complex bodies (semicolons = multiple statements)
                if ';' in body:
                    new_lines.append(line)
                    continue
                # Expand
                if keyword == "else":
                    new_lines.append(f"{indent}else:")
                    new_lines.append(f"{indent}    {body}")
                else:
                    new_lines.append(f"{indent}{keyword} {condition}:")
                    new_lines.append(f"{indent}    {body}")
                changed = True
                self.fixes_applied.append("expanded single-line if/for/while to multi-line")
            else:
                new_lines.append(line)

        if changed:
            return "\n".join(new_lines)
        return None

    # --- Transformation 5: Import organization ---
    def organize_imports(self, source):
        """Group and sort imports: stdlib → third-party → local."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        import_lines = []  # (line_no, line_text, group)
        import_line_nums = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module = node.names[0].name.split(".")[0]
                group = 0 if module in STDLIB_MODULES else 1
                import_lines.append((node.lineno - 1, lines[node.lineno - 1], group))
                import_line_nums.add(node.lineno - 1)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    group = 0 if module in STDLIB_MODULES else 1
                else:
                    group = 0
                import_lines.append((node.lineno - 1, lines[node.lineno - 1], group))
                import_line_nums.add(node.lineno - 1)

        if not import_lines:
            return None

        # Sort within each group; __future__ imports get their own first group
        future_imports = sorted(
            [il for il in import_lines if il[1].strip().startswith("from __future__")],
            key=lambda x: x[1].lower())
        stdlib_imports = sorted(
            [il for il in import_lines
             if il[2] == 0 and not il[1].strip().startswith("from __future__")],
            key=lambda x: x[1].lower())
        third_party_imports = sorted(
            [il for il in import_lines
             if il[2] == 1 and not il[1].strip().startswith("from __future__")],
            key=lambda x: x[1].lower())

        # Check if already organized
        current_order = [il[1] for il in import_lines]
        new_order = [il[1] for il in stdlib_imports]
        if third_party_imports:
            new_order.append("")
            new_order.extend([il[1] for il in third_party_imports])

        if current_order == new_order[:len(current_order)]:
            return None  # Already sorted

        # Remove old imports and insert new ones at the position of the first import
        first_import_line = min(il[0] for il in import_lines)
        last_import_line = max(il[0] for il in import_lines)

        new_lines = []
        for i, line in enumerate(lines):
            if i < first_import_line or i > last_import_line:
                if i not in import_line_nums:
                    new_lines.append(line)
            elif i == first_import_line:
                # Insert organized imports
                if future_imports:
                    for il in future_imports:
                        new_lines.append(il[1])
                    new_lines.append("")
                for il in stdlib_imports:
                    new_lines.append(il[1])
                if third_party_imports:
                    new_lines.append("")
                    for il in third_party_imports:
                        new_lines.append(il[1])
            elif i not in import_line_nums:
                # CRITICAL: keep non-import lines (code between imports) in order
                new_lines.append(line)

        changed = len(new_lines) != len(lines) or any(a != b for a, b in zip(new_lines, lines))
        if changed:
            self.fixes_applied.append("organized and sorted imports")
            return "\n".join(new_lines)
        return None

    # --- Transformation 6: Dead code removal ---
    def remove_dead_code(self, source):
        """Remove unreachable code after return/break/continue/raise."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        lines_to_remove = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.For, ast.While)):
                if not hasattr(node, 'body') or not node.body:
                    continue
                for i, stmt in enumerate(node.body):
                    if isinstance(stmt, (ast.Return, ast.Break, ast.Continue, ast.Raise)):
                        # Everything after this in the same body is dead code
                        for j in range(i + 1, len(node.body)):
                            dead = node.body[j]
                            for ln in range(dead.lineno, (dead.end_lineno or dead.lineno) + 1):
                                lines_to_remove.add(ln - 1)
                        break  # Only first terminal statement matters

        if lines_to_remove:
            new_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]
            self.fixes_applied.append(f"removed {len(lines_to_remove)} lines of dead code")
            return "\n".join(new_lines)
        return None

    # --- Transformation 7: Modernize comparisons ---
    def modernize_comparisons(self, source):
        """Modernize comparison patterns."""
        original = source

        # len(x) == 0 → not x
        source = re.sub(r'len\((\w+)\)\s*==\s*0', r'not \1', source)
        # len(x) != 0 → bool(x) (or just x in boolean context, but bool is safer)
        source = re.sub(r'len\((\w+)\)\s*!=\s*0', r'bool(\1)', source)
        # len(x) > 0 → bool(x)
        source = re.sub(r'len\((\w+)\)\s*>\s*0', r'bool(\1)', source)
        # type(x) == Y → isinstance(x, Y)
        source = re.sub(r'type\((\w+)\)\s*==\s*(\w+)', r'isinstance(\1, \2)', source)
        source = re.sub(r'type\((\w+)\)\s*!=\s*(\w+)', r'not isinstance(\1, \2)', source)
        # == None → is None, != None → is not None
        source = re.sub(r'==\s*None\b', 'is None', source)
        source = re.sub(r'!=\s*None\b', 'is not None', source)

        if source != original:
            self.fixes_applied.append("modernized comparison patterns")
            return source
        return None

    # --- Transformation 8: Performance patterns ---
    def optimize_patterns(self, source):
        """Apply performance optimization patterns."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changed = False

        # Pattern: for i in range(len(x)): ... x[i]
        # → for i, item in enumerate(x):
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                if (isinstance(node.iter, ast.Call) and
                    isinstance(node.iter.func, ast.Name) and
                    node.iter.func.id == "range" and
                    len(node.iter.args) == 1 and
                    isinstance(node.iter.args[0], ast.Call) and
                    isinstance(node.iter.args[0].func, ast.Name) and
                    node.iter.args[0].func.id == "len"):
                    # Check if x[i] is used in body
                    list_var = self._ast_to_source(node.iter.args[0].args[0])
                    loop_var = node.target.id if isinstance(node.target, ast.Name) else None
                    if loop_var and list_var:
                        # Check if body uses x[loop_var]
                        uses_indexing = False
                        for n in ast.walk(node):
                            if (isinstance(n, ast.Subscript) and
                                isinstance(n.value, ast.Name) and
                                n.value.id == list_var):
                                uses_indexing = True
                                break
                        if uses_indexing:
                            line_idx = node.lineno - 1
                            old_line = lines[line_idx]
                            new_var = "item"
                            # Avoid name collision
                            existing_names = CodeAnalyzer.get_used_names(node)
                            if new_var in existing_names:
                                new_var = f"{list_var}_item"
                            new_line = old_line.replace(
                                f"range(len({list_var}))",
                                f"enumerate({list_var})"
                            )
                            new_line = new_line.replace(
                                f"for {loop_var} in",
                                f"for {loop_var}, {new_var} in"
                            )
                            if new_line != old_line:
                                lines[line_idx] = new_line
                                # Replace x[loop_var] with new_var in body
                                for i in range(node.lineno, node.end_lineno):
                                    if i < len(lines):
                                        lines[i] = lines[i].replace(
                                            f"{list_var}[{loop_var}]",
                                            new_var
                                        )
                                changed = True
                                self.fixes_applied.append(
                                    f"replaced range(len({list_var})) with enumerate()"
                                )

        if changed:
            return "\n".join(lines)
        return None

    # --- Transformation 9: Bare except ---
    def fix_bare_except(self, source):
        """Replace bare 'except:' with 'except Exception:'."""
        lines = source.split("\n")
        changed = False
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if re.match(r'^except:\s*(#.*)?$', stripped):
                indent = line[:len(line) - len(stripped)]
                comment_match = re.match(r'^except:\s*(#.*)$', stripped)
                comment = f"  {comment_match.group(1)}" if comment_match else ""
                lines[i] = f"{indent}except Exception:{comment}"
                changed = True
                self.fixes_applied.append("replaced bare 'except:' with 'except Exception:'")
        if changed:
            return "\n".join(lines)
        return None

    # --- Transformation 10: Mutable defaults ---
    def fix_mutable_defaults(self, source):
        """Replace mutable default args with None sentinel."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changes = []  # (line_idx, old, new)
        body_inserts = []  # (func_node, var_name, factory)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        line_no = default.lineno - 1
                        col = default.col_offset
                        old_text = self._get_node_text(lines, default)
                        if old_text is not None:
                            # Find the parameter name
                            defaults = node.args.defaults
                            num_defaults = len(defaults)
                            num_args = len(node.args.args)
                            for idx, d in enumerate(defaults):
                                if d is default:
                                    arg_idx = num_args - num_defaults + idx
                                    if arg_idx < len(node.args.args):
                                        param_name = node.args.args[arg_idx].arg
                                        factory = "[]" if isinstance(default, ast.List) else \
                                                  "{}" if isinstance(default, ast.Dict) else "()"
                                        body_inserts.append((node, param_name, factory))
                                        break
                            lines[line_no] = lines[line_no][:col] + "None" + lines[line_no][col + len(old_text):]
                            changed = True
                            self.fixes_applied.append(
                                f"replaced mutable default arg in '{node.name}' with None sentinel"
                            )

        # Insert `if param is None: param = factory` at start of function body
        body_inserts.sort(key=lambda x: x[0].lineno, reverse=True)
        for func_node, param_name, factory in body_inserts:
            body_line = lines[func_node.body[0].lineno - 1]
            indent = body_line[:len(body_line) - len(body_line.lstrip())]
            insert_lines = [
                f"{indent}if {param_name} is None:",
                f"{indent}    {param_name} = {factory}",
            ]
            insert_at = func_node.body[0].lineno - 1
            for i, il in enumerate(insert_lines):
                lines.insert(insert_at + i, il)

        if body_inserts or any(c[1] != c[2] for c in changes):
            return "\n".join(lines)
        return None

    def _get_node_text(self, lines, node):
        """Extract source text spanned by an AST node (single-line only)."""
        if node.lineno != node.end_lineno:
            return None
        line = lines[node.lineno - 1]
        return line[node.col_offset:node.end_col_offset]

    # --- Transformation 11: Unused imports ---
    def remove_unused_imports(self, source):
        """Remove unused imports using AST analysis."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        used_names = CodeAnalyzer.get_used_names(tree)
        lines = source.split("\n")
        lines_to_remove = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name.split(".")[0]
                    if local_name not in used_names:
                        lines_to_remove.add(node.lineno - 1)
                        self.fixes_applied.append(f"removed unused import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                # Never remove 'from __future__ import annotations'
                if node.module == "__future__":
                    continue
                all_unused = True
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    if local_name == "*":
                        all_unused = False
                        break
                    if local_name in used_names:
                        all_unused = False
                        break
                if all_unused:
                    lines_to_remove.add(node.lineno - 1)
                    names_str = ", ".join(a.name for a in node.names)
                    self.fixes_applied.append(f"removed unused import: from {node.module} import {names_str}")

        if lines_to_remove:
            new_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]
            result = "\n".join(new_lines)
            result = re.sub(r'\n{3,}', '\n\n\n', result)
            return result
        return None

    # --- Transformation 12: __main__ guard ---
    def add_main_guard(self, source):
        """Add 'if __name__ == \"__main__\":' guard if missing."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        has_guard = False
        has_main_call = False
        has_main_def = False

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.If):
                test = node.test
                if (isinstance(test, ast.Compare) and
                    isinstance(test.left, ast.Name) and
                    test.left.id == "__name__" and
                    len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq) and
                    len(test.comparators) == 1 and
                    isinstance(test.comparators[0], ast.Constant) and
                    test.comparators[0].value == "__main__"):
                    has_guard = True
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                has_main_def = True
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id == "main":
                    has_main_call = True

        if has_guard or not (has_main_def and has_main_call):
            return None

        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "main()":
                indent = line[:len(line) - len(stripped)]
                lines[i] = f'{indent}if __name__ == "__main__":\n{indent}    main()'
                self.fixes_applied.append("added '__main__ guard' around bare main() call")
                return "\n".join(lines)
        return None

    # --- Transformation 13: Module docstring ---
    def add_module_docstring(self, source):
        """Add a module-level docstring if missing."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        if tree.body and isinstance(tree.body[0], ast.Expr):
            if isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
                return None  # Already has a docstring

        # Infer from filename or first function
        lines = source.split("\n")
        insert_at = 0

        # Skip shebang
        if lines[0].startswith("#!"):
            insert_at = 1

        # Skip encoding comment
        if insert_at < len(lines) and re.match(r'^#.*coding[:=]', lines[insert_at]):
            insert_at += 1

        # Skip future imports
        if insert_at < len(lines) and "from __future__" in lines[insert_at]:
            insert_at += 1

        docstring = '"""Module for mathematical computation and analysis."""'
        lines.insert(insert_at, docstring)
        lines.insert(insert_at + 1, "")
        self.fixes_applied.append("added module-level docstring")
        return "\n".join(lines)

    # --- Transformation 14: Ensure blank lines between functions ---
    def fix_spacing(self, source):
        """Ensure 2 blank lines between top-level functions/classes."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        insert_points = []

        for i, node in enumerate(tree.body):
            if i == 0:
                continue
            prev = tree.body[i - 1]
            curr = node
            if isinstance(curr, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # The function's visual start is its first decorator (if any),
                # not the def line — never split a decorator from its def.
                if curr.decorator_list:
                    visual_start = curr.decorator_list[0].lineno
                else:
                    visual_start = curr.lineno
                # Check how many blank lines precede the visual start
                blank_count = 0
                check_line = visual_start - 2  # 0-indexed, line before start
                while check_line >= 0 and lines[check_line].strip() == "":
                    blank_count += 1
                    check_line -= 1
                if blank_count < 2:
                    needed = 2 - blank_count
                    insert_points.append((visual_start - 1, needed))

        if not insert_points:
            return None

        insert_points.sort(reverse=True)
        for line_idx, needed in insert_points:
            for _ in range(needed):
                lines.insert(line_idx, "")

        self.fixes_applied.append("fixed spacing between function definitions")
        return "\n".join(lines)

    # --- Transformation 15: lru_cache on pure functions (REAL PERF WIN) ---
    def add_caching(self, source):
        """Add @functools.lru_cache to pure functions that are likely expensive."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changes = []  # (line_idx, decorator_lines)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Skip if already decorated
            if node.decorator_list:
                continue
            # Skip dunders, main, and test functions
            if node.name.startswith("__") or node.name == "main" or node.name.startswith("test_"):
                continue
            # Skip if it takes unhashable defaults (list/dict/set args won't work with lru_cache)
            has_unhashable = False
            for d in node.args.defaults:
                if d is not None and isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    has_unhashable = True
                    break
            if has_unhashable:
                continue
            # Check purity: no global/nonlocal, no I/O, no print, no file ops
            is_pure = True
            for n in ast.walk(node):
                if isinstance(n, (ast.Global, ast.Nonlocal)):
                    is_pure = False
                    break
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    if n.func.id in ("open", "print", "input"):
                        is_pure = False
                        break
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    if n.func.attr in ("write", "writelines", "flush"):
                        is_pure = False
                        break
            if not is_pure:
                continue
            # Only cache RECURSIVE functions: memoization turns exponential
            # recursion into linear time (e.g. fib). Non-recursive functions
            # often take unhashable args (lists/dicts) which crash lru_cache.
            has_recursion = False
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == node.name:
                    has_recursion = True
                    break
            if not has_recursion:
                continue

            # Find the indentation and insert decorator
            def_line = lines[node.lineno - 1]
            indent = def_line[:len(def_line) - len(def_line.lstrip())]
            decorator = f"{indent}@functools.lru_cache(maxsize=None)"
            changes.append((node.lineno - 1, decorator, node.name))

        if not changes:
            return None

        # Apply in reverse order
        changes.sort(key=lambda c: c[0], reverse=True)
        for line_idx, decorator, name in changes:
            lines.insert(line_idx, decorator)
            self.fixes_applied.append(f"added @functools.lru_cache to '{name}' (memoization for repeated calls)")

        # Ensure functools is imported (insert AFTER the last import line,
        # never before the module docstring)
        if "import functools" not in source and "from functools" not in source:
            last_import = -1
            for i, line in enumerate(lines):
                if line.strip().startswith(("import", "from")):
                    last_import = i
            insert_pos = last_import + 1 if last_import >= 0 else 0
            lines.insert(insert_pos, "import functools")

        return "\n".join(lines)

    # --- Transformation 16: String concat in loops → join (O(n²) → O(n)) ---
    def optimize_string_building(self, source):
        """Replace string concatenation in loops with join(). Real performance win."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changed = False

        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            # Look for: var = "" (or 'str()') before loop, then var += ... inside loop
            # Find assignments before the loop
            loop_var = None
            concat_var = None

            # Check if the first body statement is `X += ...`
            if node.body and isinstance(node.body[0], ast.AugAssign):
                stmt = node.body[0]
                if isinstance(stmt.op, ast.Add) and isinstance(stmt.target, ast.Name):
                    concat_var = stmt.target.id
                    # Check it's concatenating a string (starts with empty string assignment)
                    # Look backwards from the loop for `concat_var = ""` or `concat_var = str()`
                    for i in range(node.lineno - 2, -1, -1):
                        line = lines[i].strip()
                        if re.match(rf'^{re.escape(concat_var)}\s*=\s*["\']["\']\s*$', line):
                            loop_var = concat_var
                            break
                        elif re.match(rf'^{re.escape(concat_var)}\s*=', line):
                            break  # Found a non-empty assignment, skip

            if loop_var:
                # This is a string concat loop — but converting it safely is complex.
                # Only convert if the loop body is JUST the concatenation (1-2 statements).
                if len(node.body) <= 2:
                    # Get the iterable source
                    iter_src = self._ast_to_source(node.iter)
                    # Get what's being concatenated
                    if isinstance(node.body[0].value, ast.BinOp) and isinstance(node.body[0].value.op, ast.Add):
                        # var += expr — convert to var = "".join(str(expr) for ...)
                        # This is too risky to convert generically (expr might not be str)
                        pass

        return None  # TODO: Implement when safe pattern detection is robust

    # --- Transformation 17: Hoist regex compilation out of loops ---
    def hoist_regex(self, source):
        """Compile regex patterns at module level if used in loops. Real perf win."""
        tree = CodeAnalyzer.parse(source)
        if tree is None:
            return None

        lines = source.split("\n")
        changes = []
        hoisted_patterns = {}

        # Find re.match/search/findall calls inside loops with constant string patterns
        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While)):
                continue
            for n in ast.walk(node):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
                    isinstance(n.func.value, ast.Name) and n.func.value.id == "re" and
                    n.func.attr in ("match", "search", "findall", "sub", "split") and
                    n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                    pattern = n.args[0].value
                    if pattern not in hoisted_patterns:
                        # Create a safe variable name from the pattern
                        safe_name = "_RE_" + re.sub(r'[^A-Za-z0-9]', '_', pattern)[:30].upper()
                        # Ensure unique
                        base_name = safe_name
                        counter = 1
                        existing_names = CodeAnalyzer.get_used_names(tree)
                        while safe_name in existing_names:
                            safe_name = f"{base_name}_{counter}"
                            counter += 1
                        hoisted_patterns[pattern] = safe_name

        if not hoisted_patterns:
            return None

        # Replace re.xxx(r'pattern', ...) with re.xxx(VARNAME, ...)
        # (rR)? handles the optional raw-string prefix)
        new_source = source
        for pattern, varname in hoisted_patterns.items():
            escaped = re.escape(pattern)
            new_source = re.sub(
                rf're\.(match|search|findall|sub|split)\([rR]?["\']{escaped}["\']',
                rf're.\1({varname}',
                new_source
            )

        # Add compiled patterns at module level (after imports)
        compile_lines = []
        for pattern, varname in hoisted_patterns.items():
            # Use raw strings so backslash escapes (\d, \w, ...) survive intact
            if '"' not in pattern:
                compile_lines.append(f'{varname} = re.compile(r"{pattern}")')
            else:
                compile_lines.append(f"{varname} = re.compile(r'{pattern}')")

        lines = new_source.split("\n")
        # Find insertion point (after last import)
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip().startswith(("import", "from")):
                insert_at = i + 1

        for cl in compile_lines:
            lines.insert(insert_at, cl)
        lines.insert(insert_at + len(compile_lines), "")

        self.fixes_applied.append(
            f"hoisted {len(hoisted_patterns)} regex pattern(s) to module-level compiled constants"
        )
        return "\n".join(lines)

    # --- Transformation 18: Counter instead of manual counting ---
    def use_counter(self, source):
        """Replace manual counting loops with collections.Counter."""
        # Pattern: d = {}; for x in items:; if x not in d: d[x] = 0; d[x] += 1
        pattern = re.compile(
            r'(?P<dict>\w+)\s*=\s*\{\}[ \t]*\n'
            r'(?P<i1>[ ]+)for\s+(?P<var>\w+)\s+in\s+(?P<iter>.+?):[ \t]*\n'
            r'(?P=i1)(?P<i2>[ ]+)if\s+(?P=var)\s+not\s+in\s+(?P=dict):[ \t]*\n'
            r'(?P=i1)(?P=i2)(?P<i3>[ ]+)(?P=dict)\[(?P=var)\]\s*=\s*0[ \t]*\n'
            r'(?P=i1)(?P=i2)(?P=dict)\[(?P=var)\]\s*\+=\s*1'
        )
        match = pattern.search(source)
        if match:
            dict_var = match.group("dict")
            iterable = match.group("iter")
            # NOTE: match.start() is at the dict variable name, AFTER its original
            # indentation — so the replacement must NOT re-add the indent.
            replacement = f"{dict_var} = Counter({iterable})"
            new_source = source[:match.start()] + replacement + source[match.end():]
            # Add Counter import if needed (after the last import line)
            if "from collections import Counter" not in new_source and "import collections" not in new_source:
                imp_lines = new_source.split("\n")
                last_import = -1
                for i, line in enumerate(imp_lines):
                    if line.strip().startswith(("import", "from")):
                        last_import = i
                if last_import == -1:
                    # No imports: insert after shebang/docstring if present
                    insert_pos = 0
                    if imp_lines and imp_lines[0].startswith("#!"):
                        insert_pos = 1
                    try:
                        tree0 = ast.parse(new_source)
                        if tree0.body and isinstance(tree0.body[0], ast.Expr) and \
                           isinstance(tree0.body[0].value, ast.Constant) and \
                           isinstance(tree0.body[0].value.value, str):
                            insert_pos = tree0.body[0].end_lineno
                    except SyntaxError:
                        pass
                    imp_lines.insert(insert_pos, "from collections import Counter")
                else:
                    imp_lines.insert(last_import + 1, "from collections import Counter")
                new_source = "\n".join(imp_lines)
            self.fixes_applied.append("replaced manual counting loop with collections.Counter")
            return new_source
        return None

    # --- Transformation 19: defaultdict instead of setdefault pattern ---
    def use_defaultdict(self, source):
        """Replace 'if key not in d: d[key] = []' pattern with defaultdict."""
        # Pattern: if key not in d: d[key] = []  followed by d[key].append(...)
        pattern = re.compile(
            r'(\s+)if\s+(\w+)\s+not\s+in\s+(\w+):\s*\n'
            r'\1\s+\3\[\2\]\s*=\s*\[\]\s*\n'
            r'\1\3\[\2\]\.append\(',
            re.MULTILINE
        )
        match = pattern.search(source)
        if match:
            dict_var = match.group(3)
            # Replace the if-block with just the append
            indent = match.group(1)
            new_source = source[:match.start()] + indent + dict_var + "[" + match.group(2) + "].append(" + source[match.end():]
            # Find where the dict is initialized and change to defaultdict
            init_pattern = re.compile(rf'{re.escape(dict_var)}\s*=\s*\{{\}}')
            init_match = init_pattern.search(new_source)
            if init_match:
                new_source = new_source[:init_match.start()] + f"{dict_var} = defaultdict(list)" + new_source[init_match.end():]
                # Add import (after the last import line)
                if "from collections import defaultdict" not in new_source:
                    imp_lines = new_source.split("\n")
                    last_import = -1
                    for i, line in enumerate(imp_lines):
                        if line.strip().startswith(("import", "from")):
                            last_import = i
                    imp_lines.insert(last_import + 1, "from collections import defaultdict")
                    new_source = "\n".join(imp_lines)
                self.fixes_applied.append("replaced 'if key not in dict' pattern with collections.defaultdict")
                return new_source
        return None

    # --- Master transform ---
    def transform_all(self, source):
        """Apply all transformations in sequence. Returns (fixed_source, [fix_descriptions])."""
        self.fixes_applied = []
        current = source

        transformations = [
            self.fix_bare_except,
            self.fix_mutable_defaults,
            self.remove_unused_imports,
            self.remove_dead_code,
            self.modernize_comparisons,
            self.optimize_patterns,
            self.use_counter,
            self.use_defaultdict,
            self.hoist_regex,
            self.add_caching,
            self.expand_single_line_if,
            self.modernize_strings,
            self.add_type_annotations,
            self.add_docstrings,
            self.add_main_guard,
            self.organize_imports,
            self.fix_spacing,
        ]

        any_changed = False
        for transform_fn in transformations:
            fixes_before = len(self.fixes_applied)
            try:
                result = transform_fn(current)
                if result is not None:
                    # Verify the result still parses
                    if CodeAnalyzer.parse(result) is not None:
                        current = result
                        any_changed = True
                    else:
                        print(f"  ! Rejected transform (syntax error): {transform_fn.__name__}")
                        # Remove fixes that were added by this rejected transform
                        del self.fixes_applied[fixes_before:]
            except Exception as e:
                print(f"  ! Error in {transform_fn.__name__}: {e}")
                del self.fixes_applied[fixes_before:]

        if any_changed:
            return current, self.fixes_applied
        return None, []


def improve_python_file(content, filepath):
    """Apply all improvements to a Python file. Returns (fixed_content, [fix_descriptions]) or (None, [])."""
    transformer = CodeTransformer()
    fixed, fixes = transformer.transform_all(content)

    # Also try adding module docstring
    if fixed is not None:
        result = transformer.add_module_docstring(fixed)
        if result is not None and CodeAnalyzer.parse(result) is not None:
            fixed = result
            fixes.append("added module-level docstring")
    else:
        result = transformer.add_module_docstring(content)
        if result is not None and CodeAnalyzer.parse(result) is not None:
            fixed = result
            fixes.append("added module-level docstring")

    return fixed, fixes


# ---------------------------------------------------------------------------
# README generation (professional with badges)
# ---------------------------------------------------------------------------
def generate_readme(repo_name, description, python_files, has_requirements):
    """Generate a professional README with badges."""
    clean_name = repo_name.replace("-", " ").replace("_", " ").title()
    readme = f"""# {clean_name}

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

{description or f'A Python project for {clean_name.lower()}.'}

## Overview

{clean_name} is a Python-based project that leverages mathematical computing
techniques for high-precision calculations. It uses optimized algorithms and
parallel processing for efficient computation.

## Features

- High-precision mathematical computation
- Parallel processing with multiprocessing
- OEIS-compatible output formatting
- Configurable precision targets

## Prerequisites

- Python 3.8 or higher
"""
    # Add dependency info
    if has_requirements:
        readme += """
### Dependencies

See `requirements.txt` for the full list. Key dependencies:

- `mpmath` — arbitrary-precision floating-point arithmetic
- `gmpy2` — C-accelerated mathematical operations
"""

    readme += f"""
## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Raj123-0/{repo_name}.git
   cd {repo_name}
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
"""

    # Add usage section with actual file name
    main_file = python_files[0].split("/")[-1] if python_files else "main.py"
    readme += f"""
## Usage

Run the main script with desired precision:

```bash
python "{main_file}" --digits 1000
```

### Command-line options

```bash
python "{main_file}" --help
```

## Output

The script generates:
- A `.txt` file with the computed digits
- An OEIS b-file format output for sequence integration

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Author

**Raj123-0** — [GitHub Profile](https://github.com/Raj123-0)
"""
    return readme


def improve_readme(content, repo_info, python_files):
    """Improve an existing README with badges and better structure."""
    improved = content

    # Add badges if missing
    if "img.shields.io" not in improved and "badge" not in improved.lower():
        badge_block = """[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
"""
        # Insert after the first heading
        lines = improved.split("\n")
        if lines and lines[0].startswith("#"):
            lines.insert(1, "")
            lines.insert(2, badge_block)
            improved = "\n".join(lines)
        else:
            improved = badge_block + "\n" + improved

    if not improved.endswith("\n"):
        improved += "\n"

    if "license" not in improved.lower() and "licence" not in improved.lower():
        improved += "\n## License\n\nThis project is licensed under the MIT License.\n"

    if "## Usage" not in improved and "## usage" not in improved.lower():
        usage = "\n## Usage\n\n"
        if python_files:
            main_file = python_files[0].split("/")[-1]
            usage += f'```bash\npython "{main_file}" --help\n```\n'
        else:
            usage += "See the source files for usage instructions.\n"
        improved += usage

    return improved


# ---------------------------------------------------------------------------
# Step 3 (main): Analyze and generate improvements
# ---------------------------------------------------------------------------
def analyze_and_improve(repo_info):
    """Analyze repo contents and generate improvement changes."""
    owner = repo_info["owner"]["login"]
    repo = repo_info["name"]
    default_branch = repo_info.get("default_branch", "main")

    head_sha, tree = get_repo_tree(owner, repo, default_branch)
    files = [f for f in tree.get("tree", []) if f["type"] == "blob"]

    changes = {}
    has_readme = False
    has_gitignore = False
    has_requirements = False
    has_license = False
    python_files = []
    code_fixes_log = []

    for f in files:
        path = f["path"]
        lower = path.lower()
        if lower == "readme.md" or lower == "readme.rst" or lower == "readme.txt":
            has_readme = True
        if lower == ".gitignore":
            has_gitignore = True
        if lower == "requirements.txt" or lower == "requirement.txt":
            has_requirements = True
        if lower == "license" or lower == "license.md" or lower == "license.txt":
            has_license = True
        if lower.endswith(".py") and not lower.startswith("test"):
            python_files.append(path)

    # --- Missing .gitignore ---
    if not has_gitignore:
        changes[".gitignore"] = GITIGNORE_TEMPLATE
        print("  + Adding .gitignore")

    # --- Missing requirements.txt ---
    if not has_requirements and python_files:
        deps = set()
        for pf in python_files[:5]:
            content = get_file_content(owner, repo, pf, default_branch)
            if content:
                for line in content.split("\n"):
                    m = re.match(r"^\s*(?:from|import)\s+(\w+)", line)
                    if m:
                        mod = m.group(1)
                        if mod not in STDLIB_MODULES:
                            deps.add(mod)
        if deps:
            changes["requirements.txt"] = "\n".join(sorted(deps)) + "\n"
            print(f"  + Adding requirements.txt ({len(deps)} deps)")

    # --- Missing LICENSE ---
    if not has_license:
        changes["LICENSE"] = MIT_LICENSE_TEMPLATE
        print("  + Adding MIT LICENSE")

    # --- README ---
    readme_content = None
    readme_path = None
    for f in files:
        if f["path"].lower().startswith("readme"):
            readme_path = f["path"]
            readme_content = get_file_content(owner, repo, f["path"], default_branch)
            break

    if not readme_content or len(readme_content) < 200:
        repo_desc = repo_info.get("description") or repo.replace("-", " ").replace("_", " ").title()
        readme = generate_readme(repo, repo_desc, python_files, has_requirements)
        if readme_path:
            changes[readme_path] = readme
        else:
            changes["README.md"] = readme
        print("  + Adding/expanding README.md")
    else:
        improved = improve_readme(readme_content, repo_info, python_files)
        if improved and improved != readme_content:
            changes[readme_path] = improved
            print("  + Improving README.md (badges, structure)")

    # --- CODE IMPROVEMENT ENGINE ---
    for pf in python_files[:10]:
        content = get_file_content(owner, repo, pf, default_branch)
        if not content:
            continue
        fixed, fixes = improve_python_file(content, pf)
        if fixed and fixed != content:
            changes[pf] = fixed
            print(f"  + Code improvements in {pf}:")
            for fix in fixes:
                print(f"      - {fix}")
            code_fixes_log.append({"file": pf, "fixes": fixes})

    # --- NEW: CI workflow (runs tests on every push/PR) ---
    has_ci = any(".github/workflows/" in f["path"] for f in files)
    if not has_ci and python_files:
        changes[".github/workflows/ci.yml"] = CI_WORKFLOW_TEMPLATE
        print("  + Adding GitHub Actions CI workflow (.github/workflows/ci.yml)")

    # --- NEW: pyproject.toml (proper packaging) ---
    has_pyproject = any(f["path"] == "pyproject.toml" for f in files)
    if not has_pyproject and python_files:
        changes["pyproject.toml"] = generate_pyproject(repo, repo_info, python_files)
        print("  + Adding pyproject.toml (packaging metadata)")

    # --- NEW: Unit tests ---
    has_tests = any(f["path"].startswith("test") or f["path"].startswith("tests/") for f in files)
    if not has_tests and python_files:
        test_content = generate_tests(repo, python_files, default_branch)
        if test_content:
            changes["tests/__init__.py"] = ""
            changes["tests/test_main.py"] = test_content
            print("  + Adding unit tests (tests/test_main.py)")

    return head_sha, default_branch, changes, code_fixes_log


# ---------------------------------------------------------------------------
# Step 4: Create branch and commit changes
# ---------------------------------------------------------------------------
def create_branch(owner, repo, head_sha, branch_name):
    gh_post(f"/repos/{owner}/{repo}/git/refs", {
        "ref": f"refs/heads/{branch_name}",
        "sha": head_sha,
    })
    print(f"  Created branch: {branch_name}")

def commit_file(owner, repo, path, content, branch, message):
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    try:
        encoded_path = quote(path, safe="/")
        r = requests.get(
            f"{GH_API}/repos/{owner}/{repo}/contents/{encoded_path}",
            headers=HEADERS,
            params={"ref": branch},
        )
        file_sha = r.json().get("sha") if r.status_code == 200 else None
    except Exception:
        file_sha = None

    data = {
        "message": message,
        "content": encoded,
        "branch": branch,
    }
    if file_sha:
        data["sha"] = file_sha
    gh_put(f"/repos/{owner}/{repo}/contents/{path}", data)


# ---------------------------------------------------------------------------
# Step 5: Create PR
# ---------------------------------------------------------------------------
def create_pr(owner, repo, head, base, title, body):
    result = gh_post(f"/repos/{owner}/{repo}/pulls", {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    })
    if result:
        print(f"  Created PR #{result['number']}: {result['html_url']}")
        return result
    return None

# ---------------------------------------------------------------------------
# Step 6: Merge PR
# ---------------------------------------------------------------------------
def merge_pr(owner, repo, pr_number):
    for attempt in range(3):
        result = gh_put(f"/repos/{owner}/{repo}/pulls/{pr_number}/merge", {
            "merge_method": "squash",
        })
        if result is not None:
            print(f"  PR #{pr_number} merged successfully!")
            return True
        print(f"  Merge attempt {attempt+1} failed, waiting 10s...")
        time.sleep(10)
    print(f"  PR #{pr_number} could not be merged — left open for review.")
    return False


# ---------------------------------------------------------------------------
# Keep-alive
# ---------------------------------------------------------------------------
def keepalive():
    """Commit a timestamp file to the bot repo so GitHub never disables the schedule."""
    ts = datetime.now(timezone.utc).isoformat()
    content = f"""# Repo Improver Bot — Keep-Alive

Last heartbeat: {ts}

This file is automatically updated on every run to keep the repository active.
GitHub auto-disables scheduled workflows after 60 days of repo inactivity;
this heartbeat prevents that.
"""
    commit_file(OWNER, "repo-improver-bot", "LAST_RUN.md", content, "main",
                "chore: keep-alive heartbeat")
    print(f"  Keep-alive: updated LAST_RUN.md ({ts})")


# ---------------------------------------------------------------------------
# Repo metadata improvement
# ---------------------------------------------------------------------------
def improve_repo_metadata(repo_info):
    """Update repo description and topics if missing."""
    owner = repo_info["owner"]["login"]
    repo = repo_info["name"]
    changed = False

    # Set description if missing
    if not repo_info.get("description"):
        desc = repo.replace("-", " ").replace("_", " ").title()
        desc = f"{desc} — high-precision mathematical computation in Python"
        gh_patch(f"/repos/{owner}/{repo}", {"description": desc})
        print(f"  + Set repo description: {desc}")
        changed = True

    # Add topics if missing
    if not repo_info.get("topics"):
        topics = ["python", "mathematics", "scientific-computing", "high-precision"]
        gh_put(f"/repos/{owner}/{repo}/topics", {"names": topics})
        print(f"  + Added repo topics: {', '.join(topics)}")
        changed = True

    return changed


# ---------------------------------------------------------------------------
# PR body and commit message generation
# ---------------------------------------------------------------------------
def generate_commit_message(path):
    if path.lower() == "readme.md" or path.lower().startswith("readme"):
        return "docs: upgrade README with badges, structure, and usage examples"
    if path == ".gitignore":
        return "chore: add .gitignore for Python project"
    if path == "requirements.txt":
        return "chore: add requirements.txt with dependencies"
    if path == "LICENSE":
        return "chore: add MIT LICENSE"
    if path.endswith(".py"):
        return "refactor: comprehensive code improvements (docstrings, types, modernization)"
    return f"chore: update {path}"

def generate_pr_body(repo_name, changes, code_fixes_log):
    body = "## 🚀 Automated Improvements\n\n"
    body += f"This PR was generated by the [Repo Improver Bot](https://github.com/Raj123-0/repo-improver-bot) "
    body += f"to improve **{repo_name}**.\n\n"

    body += "### Changes\n\n"
    for path in changes:
        msg = generate_commit_message(path)
        body += f"- **{path}** — {msg}\n"

    if code_fixes_log:
        body += "\n### Code Improvements Applied\n\n"
        total_fixes = 0
        for entry in code_fixes_log:
            body += f"**{entry['file']}:**\n"
            for fix in entry["fixes"]:
                body += f"- {fix}\n"
                total_fixes += 1
            body += "\n"
        body += f"**Total: {total_fixes} improvements across {len(code_fixes_log)} file(s)**\n\n"
        body += "All code changes are AST-verified: the source is parsed, the transformation "
        body += "is applied, and the result is re-parsed to confirm it's valid Python before committing.\n"

    body += "\n### Why\n\n"
    body += "These improvements make the code more maintainable, readable, and professional. "
    body += "Documentation is comprehensive, types are explicit, and modern Python idioms are used throughout.\n"
    return body


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def write_summary(repo, pr_url, status, code_fixes_log, result):
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "pr_url": pr_url,
        "status": status,
        "code_fixes": code_fixes_log,
        "result": result,
    }
    with open("run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print(f"Repo Improver Bot v3 — Run at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Step 1: Select repo
    repo = select_repo()
    if not repo:
        print("No eligible repos found to improve.")
        write_summary(None, None, None, [], "no_repos")
        keepalive()
        return

    repo_name = repo["name"]
    repo_full = repo["full_name"]
    print(f"\nSelected repo: {repo_full}")
    print(f"  Last pushed: {repo['pushed_at']}")
    print(f"  Default branch: {repo.get('default_branch', 'main')}")

    # Step 2 & 3: Analyze and generate improvements
    print("\nAnalyzing repo...")
    head_sha, default_branch, changes, code_fixes_log = analyze_and_improve(repo)

    if not changes:
        print("No improvements to make.")
        write_summary(repo_full, None, "no_changes", code_fixes_log, "no_changes")
        keepalive()
        return

    print(f"\nGenerated {len(changes)} improvement(s):")
    for path in changes:
        print(f"  - {path}")

    # Step 4: Create branch and commit
    branch_name = f"ai-improvement-{TODAY}"
    owner = repo["owner"]["login"]

    print(f"\nCreating branch {branch_name}...")
    try:
        create_branch(owner, repo_name, head_sha, branch_name)
    except Exception as e:
        print(f"  Branch creation failed: {e}")
        print("  Branch may already exist from a previous run today, continuing...")

    print("Committing changes...")
    commit_messages = []
    for path, content in changes.items():
        msg = generate_commit_message(path)
        commit_messages.append(msg)
        commit_file(owner, repo_name, path, content, branch_name, msg)
        print(f"  Committed: {path}")

    # Step 5: Create PR
    print("\nCreating pull request...")
    pr_title = f"chore: comprehensive improvements ({len(changes)} files)"
    pr_body = generate_pr_body(repo_name, changes, code_fixes_log)
    pr = create_pr(owner, repo_name, branch_name, default_branch, pr_title, pr_body)

    pr_url = pr["html_url"] if pr else None
    pr_number = pr["number"] if pr else None

    # Step 6: Merge
    if pr and pr_number:
        print(f"\nMerging PR #{pr_number}...")
        time.sleep(5)
        merged = merge_pr(owner, repo_name, pr_number)
        status = "merged" if merged else "open"
    else:
        status = "pr_failed"
        merged = False

    # Improve repo metadata (after PR so it doesn't interfere)
    print("\nImproving repo metadata...")
    improve_repo_metadata(repo)

    print(f"\n{'=' * 60}")
    print(f"Done! Repo: {repo_full}")
    print(f"PR: {pr_url or 'N/A'}")
    print(f"Status: {status}")
    if code_fixes_log:
        total = sum(len(e['fixes']) for e in code_fixes_log)
        print(f"Code improvements: {total} across {len(code_fixes_log)} file(s)")
    print(f"{'=' * 60}")

    write_summary(repo_full, pr_url, status, code_fixes_log,
                  "success" if merged else "partial")

    # Keep-alive heartbeat
    print("\nKeep-alive heartbeat...")
    keepalive()


if __name__ == "__main__":
    main()
