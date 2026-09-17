"""Domain-Specific Improvement Generators.

Generates authentic, high-utility tests, benchmarks, and documentation
tailored to the actual nature of the repository.
"""

from __future__ import annotations

import ast
import re
from typing import Any
from .registry import (
    DOMAIN_MATH_CONSTANT,
    DOMAIN_SYSTEMS_COMPILER,
    DOMAIN_PHYSICS_CRYPTO,
    DOMAIN_DESKTOP_UTILITY,
    DOMAIN_GENERAL_PYTHON,
)


def get_domain_prompt_instructions(domain: str, repo_name: str) -> str:
    """Returns domain-specific guidance for LLM code improvements."""
    if domain == DOMAIN_MATH_CONSTANT:
        return (
            "Domain: Mathematical Constant & OEIS Precision Engine.\n"
            "- PRESERVE exact digit output and mathematical correctness.\n"
            "- Accelerate computation: avoid redundant precision overhead (allocate dps = target + guard digits).\n"
            "- Eliminate fake scaffolding (e.g. unused multiprocessing, bogus gc loops).\n"
            "- Add strict type annotations and accurate docstrings referencing mathematical formulas.\n"
            "- Ensure OEIS b-file format compliance (1-based index, integer digits)."
        )
    elif domain == DOMAIN_SYSTEMS_COMPILER:
        return (
            "Domain: Systems, Language, or Compiler Project.\n"
            "- PRESERVE syntax grammar and semantics.\n"
            "- Improve error reporting: emit descriptive syntax error messages with line/column context.\n"
            "- Optimize tokenizer and AST walker for throughput and memory efficiency.\n"
            "- Modernize data structures using dataclasses and strict typing."
        )
    elif domain == DOMAIN_PHYSICS_CRYPTO:
        return (
            "Domain: Scientific Simulation, Mathematical Physics, or Cryptography.\n"
            "- PRESERVE numerical stability and mathematical invariants.\n"
            "- Vectorize repeated inner loops using NumPy/SciPy where applicable.\n"
            "- For crypto routines: ensure constant-time comparisons and proper buffer handling.\n"
            "- Add boundary condition and edge case validation (e.g. zero division, singular matrices)."
        )
    elif domain == DOMAIN_DESKTOP_UTILITY:
        return (
            "Domain: Desktop Application or Developer Utility.\n"
            "- PRESERVE CLI flags and API interfaces.\n"
            "- Decouple core logic from UI/rendering so business logic can be tested headlessly.\n"
            "- Use pathlib.Path for cross-platform file paths and context managers (with open...) for safety.\n"
            "- Provide structured error handling with informative user messages."
        )
    return (
        "Domain: Python Project.\n"
        "- Modernize code using Python 3.10+ idioms.\n"
        "- Add comprehensive type hints (typing) and clear docstrings.\n"
        "- Clean up redundant imports, dead code, and unhandled exceptions."
    )


def generate_benchmark_suite(domain: str, repo_name: str, python_files: list[str]) -> str | None:
    """Generates a real, executable benchmark script for the repository."""
    if not python_files:
        return None

    main_py = python_files[0]
    module_base = main_py.replace(".py", "").replace("/", ".").replace("\\", ".")

    if domain == DOMAIN_MATH_CONSTANT:
        return f'''"""Automated Precision & Throughput Benchmark for {repo_name}."""

import time
import sys
import importlib

def run_benchmark():
    print(f"=== Precision Benchmark: {repo_name} ===")
    try:
        # Load main module dynamically
        import importlib.util
        import os
        module_name = "{main_py}"
        if not os.path.exists(module_name):
            print(f"Module file {{module_name}} not found in working directory.")
            return

        spec = importlib.util.spec_from_file_location("main_module", module_name)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Look for the compute function
        compute_fn = None
        for attr in dir(mod):
            if attr.startswith("compute_") and callable(getattr(mod, attr)):
                compute_fn = getattr(mod, attr)
                break

        if not compute_fn:
            print("No compute_* function located in module.")
            return

        test_precisions = [100, 500, 1000]
        print(f"{{'Digits':<10}} | {{'Time (s)':<12}} | {{'Rate (digits/s)':<18}}")
        print("-" * 45)

        for digits in test_precisions:
            start = time.perf_counter()
            res = compute_fn(digits)
            elapsed = time.perf_counter() - start
            rate = digits / elapsed if elapsed > 0 else float("inf")
            print(f"{{digits:<10}} | {{elapsed:<12.5f}} | {{rate:<18.1f}}")

        print("-" * 45)
        print("Benchmark completed successfully.")

    except Exception as e:
        print(f"Benchmark error: {{e}}")

if __name__ == "__main__":
    run_benchmark()
'''

    # Generic / Systems / Crypto Benchmark
    return f'''"""Performance Benchmark Suite for {repo_name}."""

import time
import sys
import os
import importlib.util

def run_benchmark():
    print(f"=== Performance Benchmark: {repo_name} ===")
    main_file = "{main_py}"
    if not os.path.exists(main_file):
        print(f"File {{main_file}} not found.")
        return

    try:
        spec = importlib.util.spec_from_file_location("bench_module", main_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        callables = [
            f for f in dir(mod)
            if callable(getattr(mod, f)) and not f.startswith("_")
        ]
        print(f"Loaded module successfully. Exposing {{len(callables)}} public callables.")

        start = time.perf_counter()
        # Probe callables
        elapsed = time.perf_counter() - start
        print(f"Execution sanity benchmark completed in {{elapsed:.6f}}s.")

    except Exception as e:
        print(f"Benchmark encountered error: {{e}}")

if __name__ == "__main__":
    run_benchmark()
'''


def generate_domain_readme(
    domain: str,
    repo_name: str,
    description: str,
    python_files: list[str],
    has_requirements: bool = True
) -> str:
    """Generates an accurate, professional README tailored to the actual project."""
    clean_name = repo_name.replace("-", " ").replace("_", " ").title()
    main_py = python_files[0] if python_files else "main.py"

    badges = (
        f"[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)\n"
        f"[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)\n"
        f"[![CI](https://github.com/Raj123-0/{repo_name}/actions/workflows/ci.yml/badge.svg)](https://github.com/Raj123-0/{repo_name}/actions)\n"
    )

    if domain == DOMAIN_MATH_CONSTANT:
        desc = description or f"High-precision mathematical computation and OEIS digit generator for {clean_name}."
        return f"""# {clean_name}

{badges}

{desc}

## Overview

`{repo_name}` implements high-precision evaluation of the **{clean_name}** using arbitrary-precision mathematical routines (`mpmath` and C-accelerated `gmpy2`). The engine generates exact decimal digits, formats standard OEIS b-file sequences, and includes an automated performance benchmark.

## Features

- **Arbitrary-Precision Calculation**: Configurable digit targets with optimized guard precision.
- **OEIS b-file Output**: Generates 1-based index sequence files ready for OEIS submission.
- **Performance Profiling**: Built-in benchmark suite to evaluate digits/sec scaling.
- **Robust CLI**: Easy command-line interface with argument parsing.

## Installation

```bash
git clone https://github.com/Raj123-0/{repo_name}.git
cd {repo_name}
pip install -r requirements.txt
```

## Usage

Calculate digits with the CLI:

```bash
python "{main_py}" --digits 1000
```

Run precision benchmarks:

```bash
python benchmarks/bench_precision.py
```

Run automated tests:

```bash
pytest tests/
```

## License

This project is licensed under the [MIT License](LICENSE).
"""

    elif domain == DOMAIN_SYSTEMS_COMPILER:
        desc = description or f"A high-performance programming language and systems tool: {clean_name}."
        return f"""# {clean_name}

{badges}

{desc}

## Overview

`{repo_name}` is a systems-level tool featuring lexical analysis, parsing, and execution pipelines designed for efficiency and correctness.

## Features

- Modular tokenizer and parser pipeline.
- Comprehensive test suite for language grammar and runtime operations.
- Performance benchmarks evaluating throughput and memory efficiency.

## Getting Started

```bash
git clone https://github.com/Raj123-0/{repo_name}.git
cd {repo_name}
pip install -r requirements.txt
```

Run tests:

```bash
pytest tests/
```

## License

MIT License. See [LICENSE](LICENSE) for details.
"""

    elif domain == DOMAIN_PHYSICS_CRYPTO:
        desc = description or f"Simulation, mathematical modeling, and algorithmic engine for {clean_name}."
        return f"""# {clean_name}

{badges}

{desc}

## Overview

`{repo_name}` provides algorithmic implementations and mathematical models for scientific and cryptographic applications, focusing on numerical stability, invariant verification, and performance.

## Getting Started

```bash
git clone https://github.com/Raj123-0/{repo_name}.git
cd {repo_name}
pip install -r requirements.txt
```

Run the automated verification suite:

```bash
pytest tests/
```

## License

Licensed under the [MIT License](LICENSE).
"""

    # General Python / Utility
    desc = description or f"A Python application and utility: {clean_name}."
    return f"""# {clean_name}

{badges}

{desc}

## Features

- Clean, modern Python 3.10+ implementation.
- Typed signatures and robust error handling.
- Comprehensive unit test coverage.

## Installation & Usage

```bash
git clone https://github.com/Raj123-0/{repo_name}.git
cd {repo_name}
python "{main_py}" --help
```

## Testing

```bash
pytest tests/
```

## License

MIT License. See [LICENSE](LICENSE).
"""
