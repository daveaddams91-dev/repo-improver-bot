#!/usr/bin/env python3
"""
Repo Improver Bot v4 — Hybrid Engine
====================================
LLM-driven code improvement with pattern-engine fallback.

Flow:
  1. Select the stalest eligible repo (same as v3).
  2. Run the pattern engine (v3.1) to produce a baseline improvement set
     (docstrings, import fixes, README/.gitignore/LICENSE/pyproject/tests).
  3. For each Python file (up to 3), ask an LLM (GitHub Models) to rewrite it
     with genuine improvements — algorithmic, structural, bug fixes — while
     preserving external behavior. Validate the result (AST parse, sanity
     heuristics, pytest when tests are provided). Valid LLM rewrites
     override the pattern versions.
  4. Open a PR with the combined changes and auto-merge.

If the LLM is unavailable (no Models permission, rate limit, invalid output),
the PR is simply the pattern-engine result — identical to v3.1 behavior.
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

import improve  # pattern engine (v3.1) — provides all the GitHub plumbing

GH_TOKEN = os.environ.get("GH_TOKEN", "")
# LLM provider: any OpenAI-compatible chat-completions endpoint.
#   LLM_API_KEY  — explicit API key for the provider (e.g. Groq/OpenRouter)
#   LLM_BASE_URL — provider base URL (default: GitHub Models)
#   LLM_MODEL    — model id (default: tries both models below)
# Falls back to LLM_TOKEN / GH_TOKEN against GitHub Models when no key is set.
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://models.github.ai/inference")
MODELS_ENDPOINT = LLM_BASE_URL.rstrip("/") + "/chat/completions"
DEFAULT_MODELS = ["openai/gpt-4.1-mini", "meta/Llama-3.3-70B-Instruct"]
if LLM_API_KEY:
    LLM_TOKENS = [LLM_API_KEY]
    MODELS_TO_TRY = [m for m in [os.environ.get("LLM_MODEL")] if m] or DEFAULT_MODELS
else:
    LLM_TOKENS = [t for t in (os.environ.get("LLM_TOKEN"), GH_TOKEN) if t]
    MODELS_TO_TRY = [m for m in [os.environ.get("LLM_MODEL")] if m] or DEFAULT_MODELS
MAX_FILE_BYTES = 60_000
MAX_FILES = 3
TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------
def call_llm(messages):
    """Call the configured OpenAI-compatible chat completions endpoint.

    Retries up to twice on HTTP 429 (provider rate limit, e.g. Groq free tier
    tokens-per-minute), waiting 65s for the window to reset. Returns content
    string or None.
    """
    for token in LLM_TOKENS:
        for model in MODELS_TO_TRY:
            for attempt in range(3):  # initial + up to two rate-limit retries
                payload = json.dumps({
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 16000,
                }).encode()
                req = urllib.request.Request(
                    MODELS_ENDPOINT,
                    data=payload,
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        # Cloudflare (Groq and others) blocks urllib's default UA
                        "User-Agent": "repo-improver-bot/1.0",
                    })
                try:
                    with urllib.request.urlopen(req, timeout=180) as resp:
                        data = json.loads(resp.read())
                    content = data["choices"][0]["message"]["content"]
                    if content:
                        print(f"    LLM responded via {model}")
                        return content
                except urllib.error.HTTPError as e:
                    detail = ""
                    try:
                        detail = e.read().decode()[:200]
                    except Exception:
                        pass
                    if e.code == 429 and attempt < 2:
                        print(f"    LLM {model} rate-limited (429); waiting 65s "
                              f"and retrying ({detail[:120]})")
                        time.sleep(65)
                        continue
                    print(f"    LLM {model} failed: HTTP {e.code} {detail}")
                    break
                except Exception as e:
                    print(f"    LLM {model} failed: {e}")
                    break
    return None


def parse_llm_json(content):
    """Robustly extract a JSON object from an LLM response."""
    if not content:
        return None
    text = content.strip()
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Find the outermost JSON object
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_improvement(original, improved):
    """Sanity checks on an LLM rewrite. Returns (ok, reason)."""
    if not improved or not improved.strip():
        return False, "empty output"
    try:
        ast.parse(improved)
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    # Must not be a drastic shrink (LLM truncation / lazy summary)
    if len(improved) < 0.4 * len(original):
        return False, "suspiciously short (<40% of original)"
    # Keep at least half the function/class count
    def count_defs(src):
        try:
            return sum(1 for n in ast.walk(ast.parse(src))
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        except SyntaxError:
            return 0
    if count_defs(improved) < 0.5 * count_defs(original):
        return False, "lost most definitions"
    # No placeholder text
    if "..." in improved and improved.count("...") > 5:
        return False, "too many ellipsis placeholders"
    if "TODO" in improved and "TODO" not in original:
        return False, "introduced TODO"
    return True, "ok"


def run_tests(improved_code, filename, tests_code):
    """Run the LLM's pytest suite against the improved module.

    Only runs when the module is import-safe (has a __main__ guard), so we
    never execute heavy module-level computation. Returns (ran, passed, output).
    """
    if not tests_code:
        return False, True, ""
    try:
        tree = ast.parse(improved_code)
    except SyntaxError:
        return False, False, "improved code has syntax errors"
    has_guard = any(
        isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
        and getattr(n.test.left, "id", "") == "__name__"
        for n in ast.walk(tree))
    if not has_guard:
        print("    (no __main__ guard; skipping test execution)")
        return False, True, ""

    with tempfile.TemporaryDirectory() as tmp:
        module_path = os.path.join(tmp, os.path.basename(filename))
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(improved_code)
        tests_dir = os.path.join(tmp, "tests")
        os.makedirs(tests_dir)
        with open(os.path.join(tests_dir, "test_module.py"), "w", encoding="utf-8") as f:
            f.write(tests_code.replace("MODULE_FILENAME", os.path.basename(filename)))
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "-q", tests_dir],
                capture_output=True, text=True, timeout=120, cwd=tmp)
            output = (r.stdout or "") + "\n" + (r.stderr or "")
            return True, r.returncode == 0, output
        except subprocess.TimeoutExpired:
            return True, False, "pytest timed out after 120s"


# ---------------------------------------------------------------------------
# Improvement prompt
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """Improve the file "{filename}" from the GitHub repository "{repo_name}".
{description_line}

Requirements:
1. PRESERVE external behavior exactly: same CLI arguments, same output file names and formats, same digit conventions, same essential printed messages (unless a message is factually false — e.g. fake performance claims — in which case fix it).
2. Make GENUINE improvements: fix bugs, improve algorithms and efficiency (find mathematical or data-structural shortcuts), remove unused or fake scaffolding (e.g. multiprocessing that is never used, gc.collect() theater), add type hints and docstrings where they add value, improve code structure and naming.
3. Keep the code runnable on Python 3.10+ with the same dependencies.
4. If the README or comments state a mathematical value that the code contradicts, trust the code.

Return STRICT JSON only — no markdown fences, no commentary:
{{
  "improved_code": "<complete improved file content>",
  "summary": "<concise bullet list of changes and why>",
  "tests": "<pytest test file for the improved code. Test-writing rules: (1) Load the module with importlib.util.spec_from_file_location using the literal string 'MODULE_FILENAME' as the file path — it is replaced by the real filename which may contain spaces, so always treat it as a string value, NEVER as a variable or identifier. (2) Digit strings follow the OEIS b-file convention: the leading integer-part digit is included, so constants between 0 and 1 begin with the character '0' (e.g. '083462...') — write assertions accordingly. (3) Test real behavior: known values, prefix properties, output file format. Or null if tests are impossible.>"
}}

The current file content:
```python
{source}
```"""


def llm_improve_file(repo_name, filename, source, description=None, failure_feedback=None):
    """Ask the LLM to improve one file. Returns dict or None."""
    if len(source.encode()) > MAX_FILE_BYTES:
        print(f"    Skipping {filename} (too large for LLM context)")
        return None

    desc = f"Repository description: {description}" if description else ""
    prompt = PROMPT_TEMPLATE.format(
        filename=filename, repo_name=repo_name,
        description_line=desc, source=source)
    if failure_feedback:
        prompt += ("\n\nIMPORTANT: your previous attempt at improving this file produced "
                   "an improvement or tests that FAILED. Here is the pytest output:\n\n"
                   + failure_feedback[-3000:]
                   + "\n\nFix whichever was wrong — the improved code or the tests — "
                     "and return the same JSON structure. The improved code must still "
                     "genuinely improve the original, and the tests must pass against it. "
                     "Before changing the code, check whether the failing TEST assertion "
                     "is what's wrong — e.g. it assumes no leading zero in digit strings "
                     "(OEIS convention keeps it) or misuses MODULE_FILENAME as an identifier.")
    messages = [
        {"role": "system", "content": (
            "You are an expert Python engineer who improves code while preserving "
            "its external behavior exactly. You always return valid JSON.")},
        {"role": "user", "content": prompt},
    ]
    content = call_llm(messages)
    if not content:
        return None
    parsed = parse_llm_json(content)
    if not parsed or "improved_code" not in parsed:
        print(f"    Could not parse LLM JSON response for {filename}")
        return None

    improved = parsed["improved_code"]
    summary = parsed.get("summary") or "LLM improvement"
    tests = parsed.get("tests")
    if isinstance(tests, str) and tests.strip().lower() in ("null", "none"):
        tests = None

    ok, reason = validate_improvement(source, improved)
    if not ok:
        print(f"    Validation failed for {filename}: {reason}")
        return None

    if tests:
        try:
            ast.parse(tests)
        except SyntaxError:
            print(f"    Tests have syntax errors; dropping tests for {filename}")
            tests = None

    return {"improved_code": improved, "summary": summary, "tests": tests}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print(f"Repo Improver Bot v4 (hybrid LLM) — Run at "
          f"{datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    repo = improve.select_repo()
    if not repo:
        print("No eligible repos found to improve.")
        improve.write_summary(None, None, None, [], "no_repos")
        improve.keepalive()
        return

    repo_name = repo["name"]
    repo_full = repo["full_name"]
    owner = repo["owner"]["login"]
    default_branch = repo.get("default_branch", "main")
    print(f"\nSelected repo: {repo_full}")
    print(f"  Last pushed: {repo['pushed_at']}")

    # --- Baseline: pattern-engine improvements (also adds boilerplate) ---
    print("\nPattern-engine baseline...")
    head_sha, default_branch, changes, code_fixes_log = improve.analyze_and_improve(repo)
    if not changes:
        print("Pattern engine found nothing; LLM pass will decide.")
        changes = {}

    # --- LLM enhancement pass ---
    print("\nLLM enhancement pass...")
    llm_files = []
    llm_summaries = []
    python_files = []
    try:
        _, tree_data = improve.get_repo_tree(owner, repo_name, default_branch)
        python_files = [e["path"] for e in tree_data.get("tree", [])
                        if e["path"].endswith(".py") and "/" not in e["path"]]
    except Exception as e:
        print(f"  Could not list repo files: {e}")

    for pf in python_files[:MAX_FILES]:
        print(f"  LLM improving: {pf}")
        source = improve.get_file_content(owner, repo_name, pf, default_branch)
        if not source:
            continue
        result = None
        failure = None
        for attempt in range(2):  # initial attempt + one self-repair round
            result = llm_improve_file(repo_name, pf, source, repo.get("description"),
                                      failure_feedback=failure)
            if not result:
                break
            improved = result["improved_code"]
            if improved.strip() == source.strip():
                print("    LLM returned identical code; skipping")
                result = None
                break
            ran, passed, output = run_tests(improved, pf, result["tests"])
            if ran and passed:
                print("    LLM tests passed" if attempt == 0 else "    LLM tests passed after self-repair")
                break
            if ran and not passed:
                print(f"    LLM tests FAILED (attempt {attempt + 1}); "
                      + ("sending failure back for repair" if attempt == 0 else "discarding"))
                print("    ---- pytest output (tail) ----")
                for line in output.strip().splitlines()[-15:]:
                    print(f"    | {line}")
                failure = output
                result = None
                continue
        if not result:
            continue
        improved = result["improved_code"]
        changes[pf] = improved
        if result["tests"]:
            # LLM tests replace the pattern engine's generic import-check tests
            changes["tests/test_main.py"] = result["tests"]
            changes["tests/__init__.py"] = changes.get("tests/__init__.py", "")
        llm_files.append(pf)
        llm_summaries.append(f"**{pf}**: {result['summary']}")
        code_fixes_log.append({"file": pf, "fixes": ["LLM: " + result["summary"]]})

    if not changes:
        print("No improvements to make.")
        improve.write_summary(repo_full, None, "no_changes", code_fixes_log, "no_changes")
        improve.keepalive()
        return

    print(f"\nGenerated {len(changes)} improvement(s):")
    for path in changes:
        print(f"  - {path}")

    # --- Branch / commit / PR / merge ---
    branch_name = f"llm-improvement-{TODAY}"
    print(f"\nCreating branch {branch_name}...")
    try:
        improve.create_branch(owner, repo_name, head_sha, branch_name)
    except Exception as e:
        print(f"  Branch creation failed: {e} — continuing")

    print("Committing changes...")
    for path, content in changes.items():
        msg = improve.generate_commit_message(path)
        improve.commit_file(owner, repo_name, path, content, branch_name, msg)
        print(f"  Committed: {path}")

    print("\nCreating pull request...")
    if llm_files:
        pr_title = f"AI improvement pass (LLM): {len(llm_files)} file(s) rewritten"
        pr_body = ("## LLM-driven improvements\n\n" + "\n\n".join(llm_summaries) +
                   "\n\n---\n\nAlso includes pattern-engine fixes: " +
                   ", ".join(changes.keys()))
    else:
        pr_title = f"chore: comprehensive improvements ({len(changes)} files)"
        pr_body = improve.generate_pr_body(repo_name, changes, code_fixes_log)
    pr = improve.create_pr(owner, repo_name, branch_name, default_branch, pr_title, pr_body)

    pr_url = pr["html_url"] if pr else None
    pr_number = pr["number"] if pr else None

    if pr and pr_number:
        print(f"\nMerging PR #{pr_number}...")
        time.sleep(5)
        merged = improve.merge_pr(owner, repo_name, pr_number)
        status = "merged" if merged else "open"
    else:
        status = "pr_failed"
        merged = False

    print("\nImproving repo metadata...")
    improve.improve_repo_metadata(repo)

    print(f"\n{'=' * 60}")
    print(f"Done! Repo: {repo_full}")
    print(f"PR: {pr_url or 'N/A'}")
    print(f"Status: {status}")
    print(f"LLM-improved files: {llm_files or 'none (pattern fallback)'}")
    print(f"{'=' * 60}")

    improve.write_summary(repo_full, pr_url, status, code_fixes_log,
                          "success" if merged else "partial")
    print("\nKeep-alive heartbeat...")
    improve.keepalive()


if __name__ == "__main__":
    main()
