"""Verification and Sandbox Execution Engine.

Ensures that code modifications parse cleanly, pass tests, and do not regress
functionality before any pull request is created.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from typing import Any


def validate_python_code(original: str, improved: str) -> tuple[bool, str]:
    """Validates structural correctness of an improved Python file."""
    if not improved or not improved.strip():
        return False, "Code is empty"

    try:
        ast.parse(improved)
    except SyntaxError as e:
        return False, f"Syntax error in improved code: {e}"

    # Guard against extreme truncation (LLM lazy hallucination)
    if len(improved) < 0.4 * len(original) and len(original) > 200:
        return False, "Code size decreased suspiciously (<40% of original)"

    # Defs check: count functions and classes
    def count_defs(src: str) -> int:
        try:
            tree = ast.parse(src)
            return sum(
                1 for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            )
        except SyntaxError:
            return 0

    orig_defs = count_defs(original)
    imp_defs = count_defs(improved)
    if orig_defs > 2 and imp_defs < 0.5 * orig_defs:
        return False, f"Lost more than half of original definitions ({imp_defs} vs {orig_defs})"

    # Guard against lazy placeholder ellipsis
    if improved.count("...") > original.count("...") + 3:
        return False, "Introduced ellipsis (...) placeholders"

    return True, "Valid"


def run_pytest_sandbox(
    module_code: str,
    module_rel_path: str,
    test_code: str,
    timeout_sec: int = 90
) -> tuple[bool, str]:
    """Runs a generated pytest test suite against the target module in an isolated tempdir.

    Returns:
        (passed: bool, output: str)
    """
    if not test_code or not test_code.strip():
        return True, "No tests provided"

    # Verify test code syntax before running
    try:
        ast.parse(test_code)
    except SyntaxError as e:
        return False, f"Test code has syntax error: {e}"

    with tempfile.TemporaryDirectory(prefix="improver_sandbox_") as tmpdir:
        # Recreate file structure if file is in a subdirectory
        target_path = os.path.join(tmpdir, os.path.basename(module_rel_path))
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(module_code)

        tests_dir = os.path.join(tmpdir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        test_file = os.path.join(tests_dir, "test_generated.py")

        # Substitute MODULE_FILENAME placeholder with absolute path
        normalized_test = test_code.replace("MODULE_FILENAME", target_path.replace("\\", "/"))
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(normalized_test)

        try:
            cmd = [sys.executable, "-m", "pytest", "-x", "-q", tests_dir]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=tmpdir
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            return res.returncode == 0, output.strip()

        except subprocess.TimeoutExpired:
            return False, f"Pytest execution timed out after {timeout_sec}s"
        except Exception as e:
            return False, f"Error running sandbox pytest: {e}"
