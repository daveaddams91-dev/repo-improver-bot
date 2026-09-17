"""Unit tests for Verifier and Sandbox execution."""

from core.verifier import validate_python_code, run_pytest_sandbox


def test_validate_python_code_valid():
    orig = "def add(a, b):\n    return a + b\n"
    imp = "def add(a: int, b: int) -> int:\n    '''Add two ints.'''\n    return a + b\n"
    valid, reason = validate_python_code(orig, imp)
    assert valid is True
    assert reason == "Valid"


def test_validate_python_code_syntax_error():
    orig = "def add(a, b): return a + b\n"
    imp = "def add(a, b): return a + \n"
    valid, reason = validate_python_code(orig, imp)
    assert valid is False
    assert "Syntax error" in reason


def test_validate_python_code_truncation():
    orig = "def f1(): pass\ndef f2(): pass\ndef f3(): pass\ndef f4(): pass\n" * 20
    imp = "def f1(): pass\n"
    valid, reason = validate_python_code(orig, imp)
    assert valid is False
    assert "suspiciously" in reason or "Lost more than half" in reason


def test_run_pytest_sandbox_passing():
    mod_code = """
def multiply(x, y):
    return x * y
"""
    test_code = """
import importlib.util

spec = importlib.util.spec_from_file_location("mod", "MODULE_FILENAME")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_multiply():
    assert mod.multiply(3, 4) == 12
"""
    passed, out = run_pytest_sandbox(mod_code, "my_math.py", test_code)
    assert passed is True


def test_run_pytest_sandbox_failing():
    mod_code = """
def multiply(x, y):
    return x + y  # Bug!
"""
    test_code = """
import importlib.util

spec = importlib.util.spec_from_file_location("mod", "MODULE_FILENAME")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_multiply():
    assert mod.multiply(3, 4) == 12
"""
    passed, out = run_pytest_sandbox(mod_code, "my_math.py", test_code)
    assert passed is False
    assert "assert" in out or "FAILED" in out
