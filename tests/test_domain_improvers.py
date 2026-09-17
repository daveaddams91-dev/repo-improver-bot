"""Unit tests for domain improvers (benchmarks, READMEs, prompts)."""

from core.registry import DOMAIN_MATH_CONSTANT, DOMAIN_PHYSICS_CRYPTO, DOMAIN_SYSTEMS_COMPILER
from core.domain_improvers import (
    generate_benchmark_suite,
    generate_domain_readme,
    get_domain_prompt_instructions,
)


def test_generate_benchmark_suite_math():
    code = generate_benchmark_suite(DOMAIN_MATH_CONSTANT, "Universal-Parabolic-Constant", ["Universal Parabolic Constant.py"])
    assert code is not None
    assert "Precision Benchmark" in code
    assert "compute_" in code
    assert "perf_counter" in code


def test_generate_benchmark_suite_generic():
    code = generate_benchmark_suite(DOMAIN_PHYSICS_CRYPTO, "Tokamak-Py", ["tokamak.py"])
    assert code is not None
    assert "Performance Benchmark: Tokamak-Py" in code


def test_generate_domain_readme_not_hardcoded_oeis():
    readme = generate_domain_readme(DOMAIN_PHYSICS_CRYPTO, "Tokamak-Py", "Tokamak plasma simulation", ["tokamak.py"])
    assert "Tokamak-Py" in readme
    assert "scientific and cryptographic applications" in readme
    assert "OEIS" not in readme  # Crucial: non-math repos must NOT claim to be OEIS constant calculators!


def test_generate_domain_readme_math_oeis():
    readme = generate_domain_readme(DOMAIN_MATH_CONSTANT, "Universal-Parabolic-Constant", "", ["Universal Parabolic Constant.py"])
    assert "Universal Parabolic Constant" in readme
    assert "OEIS" in readme
    assert "benchmarks/bench_precision.py" in readme


def test_get_domain_prompt_instructions():
    instr_math = get_domain_prompt_instructions(DOMAIN_MATH_CONSTANT, "Universal-Parabolic-Constant")
    assert "Mathematical Constant" in instr_math

    instr_crypto = get_domain_prompt_instructions(DOMAIN_PHYSICS_CRYPTO, "AegisCrypt")
    assert "Cryptography" in instr_crypto or "Simulation" in instr_crypto
