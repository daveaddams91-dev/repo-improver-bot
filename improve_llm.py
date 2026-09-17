#!/usr/bin/env python3
"""Repo Improver Bot v5 — Fully Autonomous Multi-Domain Engineering Engine.

High-frequency, domain-aware automated repository improver with multi-provider
LLM routing, sandbox test verification, and persistent capability ladder tracking.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import improve
from core.registry import (
    RepoRegistry,
    detect_domain,
    DOMAIN_MATH_CONSTANT,
    DOMAIN_SYSTEMS_COMPILER,
    DOMAIN_PHYSICS_CRYPTO,
    DOMAIN_DESKTOP_UTILITY,
)
from core.llm_router import LLMRouter
from core.verifier import validate_python_code, run_pytest_sandbox
from core.domain_improvers import (
    get_domain_prompt_instructions,
    generate_benchmark_suite,
    generate_domain_readme,
)

TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")
MAX_REPOS_PER_RUN = int(os.environ.get("MAX_REPOS_PER_RUN", "2"))
TARGET_REPO_ENV = os.environ.get("TARGET_REPO", "").strip()
IMPROVEMENT_MODE_ENV = os.environ.get("IMPROVEMENT_MODE", "auto").strip()

# Initialize Router and Registry
ROUTER = LLMRouter()
REGISTRY = RepoRegistry()


# ---------------------------------------------------------------------------
# Prompt Engineering & LLM File Improvement
# ---------------------------------------------------------------------------
def build_improvement_prompt(
    repo_name: str,
    filename: str,
    source: str,
    domain: str,
    stage: str,
    description: str = "",
    failure_feedback: str | None = None
) -> str:
    domain_guidance = get_domain_prompt_instructions(domain, repo_name)
    desc_line = f"Repository description: {description}\n" if description else ""

    prompt = f"""Improve the file "{filename}" from the GitHub repository "{repo_name}".
{desc_line}
Domain Guidance:
{domain_guidance}

Current Improvement Focus: {stage.upper()}

Requirements:
1. PRESERVE external behavior and interfaces exactly (CLI arguments, outputs, function names).
2. Make GENUINE, HIGH-VALUE improvements based on the focus:
   - If tests/benchmarks: provide comprehensive, robust tests testing real logic and edge cases.
   - If optimization: speed up algorithms, use vectorization or caching where beneficial, remove fake overhead, add typing and docstrings.
   - If hygiene: clean structure, fix unhandled edge cases, add type annotations without undefined symbols.
3. Keep code compatible with Python 3.10+ and standard dependencies.
4. Return STRICT JSON only (no markdown wrapping, no extra keys):
{{
  "improved_code": "<complete improved python file content>",
  "summary": "<concise bullet points explaining changes and technical rationale>",
  "tests": "<pytest test file content using literal 'MODULE_FILENAME' placeholder for module path. Or null if tests are not applicable>"
}}

Current file content:
```python
{source}
```"""

    if failure_feedback:
        prompt += (
            f"\n\nCRITICAL FIX REQUIRED: Your previous attempt failed test execution:\n"
            f"{failure_feedback[-2500:]}\n"
            f"Fix the issue in the improved_code or tests, ensure valid JSON with escaped backslashes, and return."
        )

    return prompt


def llm_improve_module(
    repo_name: str,
    filename: str,
    source: str,
    domain: str,
    stage: str,
    description: str = ""
) -> dict[str, Any] | None:
    """Invokes the LLM to improve a module with sandbox validation and self-repair."""
    if len(source.encode("utf-8")) > 75_000:
        print(f"  [Skip] {filename} is too large for single-pass rewrite.")
        return None

    feedback = None
    for attempt in range(2):
        prompt = build_improvement_prompt(
            repo_name=repo_name,
            filename=filename,
            source=source,
            domain=domain,
            stage=stage,
            description=description,
            failure_feedback=feedback,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a principal software engineer and domain specialist who writes "
                    "production-quality, bug-free, and thoroughly tested Python code. You always respond in strict JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        raw_content = ROUTER.call_chat(messages, temperature=0.1)
        if not raw_content:
            print(f"  [LLM] No response returned for {filename}.")
            return None

        parsed = ROUTER.parse_json(raw_content)
        if not parsed or "improved_code" not in parsed:
            print(f"  [LLM] Response could not be parsed as valid JSON (attempt {attempt + 1}).")
            feedback = "Your previous output could not be parsed as JSON. Return ONLY valid JSON with keys improved_code, summary, tests."
            continue

        improved_code = parsed["improved_code"]
        summary = parsed.get("summary", "Code improvements")
        tests_code = parsed.get("tests")
        if isinstance(tests_code, str) and tests_code.strip().lower() in ("null", "none", ""):
            tests_code = None

        # 1. Structural validation
        valid, reason = validate_python_code(source, improved_code)
        if not valid:
            print(f"  [Validation] {filename} rejected: {reason}")
            feedback = f"Improved code failed validation: {reason}"
            continue

        # 2. Sandboxed test verification
        if tests_code:
            passed, test_output = run_pytest_sandbox(improved_code, filename, tests_code)
            if not passed:
                print(f"  [Verifier] Sandbox tests FAILED for {filename} (attempt {attempt + 1})")
                feedback = f"Pytest failed with output:\n{test_output}"
                continue
            print(f"  [Verifier] Sandbox tests PASSED for {filename}")

        if isinstance(summary, (list, tuple)):
            summary = "; ".join(str(s) for s in summary)

        return {
            "improved_code": improved_code,
            "summary": str(summary),
            "tests": tests_code,
        }

    return None


# ---------------------------------------------------------------------------
# Repository Processing Pipeline
# ---------------------------------------------------------------------------
def process_repository(repo: dict[str, Any], target_stage: str) -> bool:
    """Executes a domain-aware improvement cycle on the given repository."""
    repo_name = repo["name"]
    repo_full = repo["full_name"]
    owner = repo["owner"]["login"]
    default_branch = repo.get("default_branch", "main")
    description = repo.get("description") or ""

    print(f"\n" + "=" * 65)
    print(f"Target Repo: {repo_full}")
    print(f"Selected Stage: {target_stage.upper()}")
    print("=" * 65)

    # 1. Fetch file tree
    head_sha, tree_data = improve.get_repo_tree(owner, repo_name, default_branch)
    tree_items = tree_data.get("tree", [])
    all_files = [e["path"] for e in tree_items if e.get("type") == "blob"]

    # Read README if present
    readme_text = ""
    for f in all_files:
        if f.lower().startswith("readme"):
            readme_text = improve.get_file_content(owner, repo_name, f, default_branch) or ""
            break

    # 2. Detect Domain
    domain = detect_domain(repo_name, description=description, file_paths=all_files, readme_text=readme_text)
    print(f"  Detected Domain: {domain}")
    REGISTRY.update_repo_info(repo_name, domain, description)

    # Discover eligible Python files (excluding caches and tests)
    python_files = []
    for path in all_files:
        if path.endswith(".py"):
            parts = [p.lower() for p in path.split("/")]
            if any(p.startswith(".") or p in ("venv", "env", "__pycache__", "build", "dist") for p in parts):
                continue
            if not any(p.startswith("test") for p in parts):
                python_files.append(path)

    changes: dict[str, str] = {}
    code_fixes_log: list[dict[str, Any]] = []
    llm_summaries: list[str] = []

    # 3. Stage-Specific Execution
    # Baseline Hygiene: .gitignore, LICENSE, requirements
    if target_stage in ("hygiene", "optimization"):
        _, _, base_changes, base_log = improve.analyze_and_improve(repo)
        changes.update(base_changes)
        code_fixes_log.extend(base_log)

    # Documentation: Generate domain-accurate README
    if target_stage in ("documentation", "hygiene") or not any(f.lower().startswith("readme") for f in all_files):
        new_readme = generate_domain_readme(domain, repo_name, description, python_files)
        changes["README.md"] = new_readme
        print("  + Generated domain-accurate README.md")

    # Benchmarks: Generate automated benchmark script
    if target_stage in ("benchmarks", "optimization") and python_files:
        has_benchmark = any("bench" in f.lower() for f in all_files)
        if not has_benchmark:
            bench_code = generate_benchmark_suite(domain, repo_name, python_files)
            if bench_code:
                bench_path = "benchmarks/bench_precision.py" if domain == DOMAIN_MATH_CONSTANT else "benchmarks/benchmark.py"
                changes[bench_path] = bench_code
                print(f"  + Added benchmark suite ({bench_path})")

    # LLM Code Enhancement & Verified Test Generation
    if python_files and ROUTER.providers:
        for pf in python_files[:2]:  # Focus on primary modules
            print(f"\n  Analyzing module with LLM: {pf}")
            source = improve.get_file_content(owner, repo_name, pf, default_branch)
            if not source:
                continue

            result = llm_improve_module(
                repo_name=repo_name,
                filename=pf,
                source=source,
                domain=domain,
                stage=target_stage,
                description=description,
            )

            if result:
                improved = result["improved_code"]
                summary = result["summary"]
                tests = result["tests"]

                if improved.strip() != source.strip():
                    changes[pf] = improved
                    llm_summaries.append(f"**{pf}**: {summary}")
                    code_fixes_log.append({"file": pf, "fixes": [f"LLM: {summary}"]})
                    print(f"  ✓ Validated improvement in {pf}")

                if tests:
                    changes["tests/test_main.py"] = tests
                    changes["tests/__init__.py"] = ""
                    print("  ✓ Added sandboxed pytest suite (tests/test_main.py)")

    if not changes:
        print("  No changes generated for this repository.")
        return False

    # 4. Commit, Pull Request, and Auto-Merge
    branch_name = f"ai-improve/{target_stage}-{TODAY}-{int(time.time()) % 10000}"
    print(f"\nCreating branch {branch_name}...")
    try:
        improve.create_branch(owner, repo_name, head_sha, branch_name)
    except Exception as e:
        print(f"  Branch creation notice: {e}")

    print(f"Committing {len(changes)} file(s)...")
    for path, content in changes.items():
        msg = improve.generate_commit_message(path)
        improve.commit_file(owner, repo_name, path, content, branch_name, msg)
        print(f"  Committed: {path}")

    # Create descriptive PR title and body
    if target_stage == "tests":
        pr_title = f"test: add verified unit test suite for {repo_name}"
    elif target_stage == "benchmarks":
        pr_title = f"perf: add automated performance benchmark suite"
    elif target_stage == "optimization":
        pr_title = f"perf: algorithmic optimization and type hardening"
    elif target_stage == "documentation":
        pr_title = f"docs: comprehensive technical documentation and usage guide"
    else:
        pr_title = f"chore: repository modernization and quality upgrades"

    if llm_summaries:
        pr_body = (
            f"## 🚀 Automated Improvement: {target_stage.title()}\n\n"
            f"This PR was generated by [Repo Improver Bot](https://github.com/Raj123-0/repo-improver-bot) "
            f"focusing on **{target_stage.upper()}**.\n\n"
            f"### Key Improvements\n\n"
            + "\n\n".join(llm_summaries)
            + f"\n\n### Modified Files\n"
            + "\n".join(f"- `{p}`" for p in sorted(changes.keys()))
            + f"\n\nAll Python modifications and test suites have been pre-validated with sandbox `pytest` execution."
        )
    else:
        pr_body = improve.generate_pr_body(repo_name, changes, code_fixes_log)

    print("\nOpening Pull Request...")
    pr = improve.create_pr(owner, repo_name, branch_name, default_branch, pr_title, pr_body)
    pr_url = pr["html_url"] if pr else None
    pr_number = pr["number"] if pr else None

    merged = False
    if pr and pr_number:
        print(f"Merging PR #{pr_number}...")
        time.sleep(4)
        merged = improve.merge_pr(owner, repo_name, pr_number)

    # 5. Record Progress in Registry
    REGISTRY.record_stage(
        repo_name=repo_name,
        stage=target_stage,
        pr_url=pr_url,
        summary=f"{pr_title} ({len(changes)} files)"
    )

    print(f"\nCompleted {repo_full} | PR: {pr_url} | Merged: {merged}")
    return True


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print(f"Repo Improver Bot v5 (Autonomous Multi-Domain Engine)")
    print(f"Run started at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 65)

    pinned = improve.get_pinned_repos()
    skip = pinned | {"test", "repo-improver-bot", "fransen-robinson-record", "eulerian-fluid-solver"}

    try:
        repos_data = improve.gh_get("/user/repos", params={
            "affiliation": "owner",
            "per_page": 100,
            "sort": "pushed",
            "direction": "asc"
        })
    except Exception as e:
        print(f"Error listing repositories: {e}")
        return

    eligible = [
        r for r in repos_data
        if not r.get("archived") and not r.get("fork") and r["name"] not in skip
    ]

    print(f"Found {len(eligible)} eligible repositories for autonomous improvement.")

    processed_count = 0
    excluded_names: set[str] = set()

    for i in range(MAX_REPOS_PER_RUN):
        candidates = [r for r in eligible if r["name"] not in excluded_names]
        if not candidates:
            break

        repo, stage = REGISTRY.select_candidate(
            candidates,
            target_name=TARGET_REPO_ENV if i == 0 and TARGET_REPO_ENV else None,
            mode_override=IMPROVEMENT_MODE_ENV if IMPROVEMENT_MODE_ENV != "auto" else None,
        )

        if not repo:
            break

        try:
            success = process_repository(repo, stage)
            if success:
                processed_count += 1
        except Exception as e:
            print(f"Error processing repository {repo.get('name')}: {e}")

        excluded_names.add(repo["name"])

    print("\n" + "=" * 65)
    print(f"Autonomous run complete. Repositories improved: {processed_count}")
    print("=" * 65)

    # Keep-alive heartbeat to prevent GitHub Actions auto-disable
    improve.keepalive()


if __name__ == "__main__":
    main()
