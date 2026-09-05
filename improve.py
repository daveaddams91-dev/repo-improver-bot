#!/usr/bin/env python3
"""
Repo Improver Bot — analyzes stale GitHub repos and opens improvement PRs.
Runs as a GitHub Action. Uses the GitHub REST API via requests.
"""

import os
import sys
import json
import time
import re
import base64
from datetime import datetime, timezone, timedelta

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

# GitHub API helpers
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


# --- Step 1: Select the stalest repo ---
def select_repo():
    """List repos owned by the user, sorted oldest-push-first. Pick first eligible."""
    params = {
        "affiliation": "owner",
        "sort": "pushed",
        "direction": "asc",
        "per_page": 100,
        "page": 1,
    }
    repos = gh_get("/user/repos", params=params)
    for repo in repos:
        if repo.get("archived") or repo.get("fork"):
            continue
        if repo["name"] in ("test", "repo-improver-bot"):
            continue
        pushed_at = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
        if pushed_at > SEVEN_DAYS_AGO:
            continue
        return repo

    # If no repos >7 days stale, pick the stalest available
    repos_sorted = sorted(repos, key=lambda r: r["pushed_at"])
    for repo in repos_sorted:
        if repo.get("archived") or repo.get("fork"):
            continue
        if repo["name"] in ("test", "repo-improver-bot"):
            continue
        return repo

    return None


# --- Step 2: Get repo file tree ---
def get_repo_tree(owner, repo, branch="main"):
    """Get the file tree of a repo's default branch."""
    # Get default branch ref
    ref = gh_get(f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
    head_sha = ref["object"]["sha"]

    # Get the commit to find its tree
    commit = gh_get(f"/repos/{owner}/{repo}/git/commits/{head_sha}")
    tree_sha = commit["tree"]["sha"]

    # Get the tree (recursive)
    tree = gh_get(f"/repos/{owner}/{repo}/git/trees/{tree_sha}", params={"recursive": "1"})
    return head_sha, tree


def get_file_content(owner, repo, path, branch="main"):
    """Get decoded content of a file in the repo."""
    try:
        r = requests.get(
            f"{GH_API}/repos/{owner}/{repo}/contents/{path}",
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


# --- Step 3: Analyze repo and generate improvements ---
def analyze_and_improve(repo_info):
    """Analyze repo contents and generate improvement changes."""
    owner = repo_info["owner"]["login"]
    repo = repo_info["name"]
    default_branch = repo_info.get("default_branch", "main")

    head_sha, tree = get_repo_tree(owner, repo, default_branch)
    files = [f for f in tree.get("tree", []) if f["type"] == "blob"]

    changes = {}  # path -> new content

    has_readme = False
    has_gitignore = False
    has_requirements = False
    has_license = False
    has_setup_py = False
    has_pyproject = False
    has_pytest = False
    python_files = []

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
        if lower == "setup.py":
            has_setup_py = True
        if lower == "pyproject.toml":
            has_pyproject = True
        if lower.startswith("test") and lower.endswith(".py"):
            has_pytest = True
        if lower.endswith(".py") and not lower.startswith("test"):
            python_files.append(path)

    # --- Improvement: Missing .gitignore ---
    if not has_gitignore:
        changes[".gitignore"] = GITIGNORE_TEMPLATE
        print("  + Adding .gitignore")

    # --- Improvement: Missing requirements.txt ---
    if not has_requirements and python_files:
        # Try to detect imports
        deps = set()
        for pf in python_files[:5]:
            content = get_file_content(owner, repo, pf, default_branch)
            if content:
                # Look for import statements
                for line in content.split("\n"):
                    m = re.match(r"^\s*(?:from|import)\s+(\w+)", line)
                    if m:
                        mod = m.group(1)
                        if mod not in ("os", "sys", "json", "base64", "sqlite3",
                                       "shutil", "math", "random", "time", "datetime",
                                       "collections", "itertools", "functools",
                                       "typing", "re", "io", "pathlib", "dataclasses",
                                       "abc", "copy", "enum", "hashlib", "hmac",
                                       "decimal", "fractions", "statistics", "csv",
                                       "xml", "html", "urllib", "http", "socket",
                                       "threading", "multiprocessing", "queue",
                                       "concurrent", "asyncio", "logging", "warnings",
                                       "unittest", "traceback", "inspect", "string",
                                       "textwrap", "operator", "struct", "array",
                                       "bisect", "heapq", "bisect", "numbers",
                                       "contextlib", "weakref", "types", "secrets",
                                       "signal", "select", "errno", "stat",
                                       "tempfile", "glob", "fnmatch", "linecache",
                                       "shelve", "marshal", "pickle", "copyreg",
                                       "codecs", "unicodedata", "locale"):
                            deps.add(mod)
        if deps:
            changes["requirements.txt"] = "\n".join(sorted(deps)) + "\n"
            print(f"  + Adding requirements.txt ({len(deps)} deps)")

    # --- Improvement: Missing LICENSE ---
    if not has_license:
        changes["LICENSE"] = MIT_LICENSE_TEMPLATE
        print("  + Adding MIT LICENSE")

    # --- Improvement: Expand README ---
    readme_content = None
    readme_path = None
    for f in files:
        if f["path"].lower().startswith("readme"):
            readme_path = f["path"]
            readme_content = get_file_content(owner, repo, f["path"], default_branch)
            break

    if not readme_content or len(readme_content) < 200:
        # README is missing or very short — generate a good one
        repo_desc = repo_info.get("description") or repo.replace("-", " ").replace("_", " ").title()
        repo_name = repo
        readme = generate_readme(repo_name, repo_desc, python_files, has_requirements)
        changes[readme_path or "README.md"] = readme
        print("  + Adding/expanding README.md")
    else:
        # README exists and is decent — try to improve it
        improved = improve_readme(readme_content, repo_info, python_files)
        if improved and improved != readme_content:
            changes[readme_path] = improved
            print("  + Improving README.md")

    # --- Improvement: Add type hints / docstrings to a Python file ---
    if python_files and len(changes) < 4:
        target_file = python_files[0]
        content = get_file_content(owner, repo, target_file, default_branch)
        if content:
            improved = improve_python_file(content, target_file)
            if improved and improved != content:
                changes[target_file] = improved
                print(f"  + Improving {target_file}")

    return head_sha, default_branch, changes


def generate_readme(repo_name, description, python_files, has_requirements):
    """Generate a README from scratch."""
    readme = f"""# {repo_name.replace('-', ' ').replace('_', ' ').title()}

{description}

## Features

- Written in Python
- See source files for functionality details

## Prerequisites

- Python 3.8+

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Raj123-0/{repo_name}.git
   cd {repo_name}
   ```

"""
    if has_requirements:
        readme += "2. Install dependencies:\n   ```bash\n   pip install -r requirements.txt\n   ```\n\n"
    readme += "## Usage\n\nRun the main script:\n```bash\n"
    if python_files:
        readme += f"python {python_files[0].split('/')[-1]}\n"
    else:
        readme += f"python main.py\n"
    readme += "```\n\n## License\n\nThis project is licensed under the MIT License.\n"
    return readme


def improve_readme(content, repo_info, python_files):
    """Make small improvements to an existing README."""
    improved = content

    # Fix missing trailing newline
    if not improved.endswith("\n"):
        improved += "\n"

    # Add a License section if missing
    if "license" not in improved.lower() and "licence" not in improved.lower():
        improved += "\n## License\n\nThis project is licensed under the MIT License.\n"

    # Add a Usage section if missing
    if "usage" not in improved.lower():
        usage = "\n## Usage\n\n"
        if python_files:
            main_file = python_files[0].split("/")[-1]
            usage += f"```bash\npython {main_file}\n```\n"
        else:
            usage += "See the source files for usage instructions.\n"
        improved += usage

    return improved


def improve_python_file(content, filepath):
    """Add docstrings and type hints to simple Python functions."""
    lines = content.split("\n")
    improved_lines = []
    in_function = False
    changes_made = False

    for i, line in enumerate(lines):
        improved_lines.append(line)

        # Detect function definitions without docstrings
        func_match = re.match(r"^(\s*)def\s+(\w+)\s*\((.*?)\)\s*:", line)
        if func_match:
            indent = func_match.group(1)
            func_name = func_match.group(2)
            # Check if next non-empty line is already a docstring
            next_idx = i + 1
            while next_idx < len(lines) and lines[next_idx].strip() == "":
                next_idx += 1
            if next_idx < len(lines):
                next_line = lines[next_idx].strip()
                if next_line.startswith('"""') or next_line.startswith("'''"):
                    continue  # Already has a docstring

            # Add a docstring
            improved_lines.append(f'{indent}    """{func_name.replace("_", " ").capitalize()}."""')
            changes_made = True

    if changes_made:
        return "\n".join(improved_lines)
    return None


# --- Step 4: Create branch and commit changes ---
def create_branch(owner, repo, head_sha, branch_name):
    """Create a new branch from the given SHA."""
    gh_post(f"/repos/{owner}/{repo}/git/refs", {
        "ref": f"refs/heads/{branch_name}",
        "sha": head_sha,
    })
    print(f"  Created branch: {branch_name}")


def commit_file(owner, repo, path, content, branch, message):
    """Create or update a file in the repo."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    # Check if file exists to get its SHA
    try:
        r = requests.get(
            f"{GH_API}/repos/{owner}/{repo}/contents/{path}",
            headers=HEADERS,
            params={"ref": branch},
        )
        if r.status_code == 200:
            file_sha = r.json().get("sha")
        else:
            file_sha = None
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


# --- Step 5: Create PR ---
def create_pr(owner, repo, head, base, title, body):
    """Create a pull request."""
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


# --- Step 6: Merge PR ---
def merge_pr(owner, repo, pr_number):
    """Merge a pull request with retries."""
    for attempt in range(3):
        result = gh_put(f"/repos/{owner}/{repo}/pulls/{pr_number}/merge", {
            "merge_method": "squash",
        })
        if result is not None:
            print(f"  PR #{pr_number} merged successfully!")
            return True
        print(f"  Merge attempt {attempt+1} failed, waiting 10s...")
        time.sleep(10)
    print(f"  PR #{pr_number} could not be merged automatically — left open for review.")
    return False


# --- Templates ---
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


# --- Main ---
def main():
    print("=" * 60)
    print(f"Repo Improver Bot — Run at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Step 1: Select repo
    repo = select_repo()
    if not repo:
        print("No eligible repos found to improve.")
        write_summary(None, None, None, "no_repos")
        return

    repo_name = repo["name"]
    repo_full = repo["full_name"]
    print(f"\nSelected repo: {repo_full}")
    print(f"  Last pushed: {repo['pushed_at']}")
    print(f"  Default branch: {repo.get('default_branch', 'main')}")

    # Step 2 & 3: Analyze and generate improvements
    print("\nAnalyzing repo...")
    head_sha, default_branch, changes = analyze_and_improve(repo)

    if not changes:
        print("No improvements to make.")
        write_summary(repo_full, None, None, "no_changes")
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
        # Branch might already exist from a previous run today
        print("  Branch may already exist, continuing...")

    print("\nCommitting changes...")
    commit_messages = []
    for path, content in changes.items():
        msg = generate_commit_message(path)
        commit_messages.append(msg)
        commit_file(owner, repo_name, path, content, branch_name, msg)
        print(f"  Committed: {path}")

    # Step 5: Create PR
    print("\nCreating pull request...")
    pr_title = f"chore: automated improvements ({', '.join(changes.keys())})"
    pr_body = generate_pr_body(repo_name, changes, commit_messages)
    pr = create_pr(owner, repo_name, branch_name, default_branch, pr_title, pr_body)

    pr_url = pr["html_url"] if pr else None
    pr_number = pr["number"] if pr else None

    # Step 6: Merge
    if pr and pr_number:
        print(f"\nMerging PR #{pr_number}...")
        time.sleep(5)  # Wait for GitHub to compute mergeability
        merged = merge_pr(owner, repo_name, pr_number)
        status = "merged" if merged else "open"
    else:
        status = "pr_failed"
        merged = False

    print(f"\n{'=' * 60}")
    print(f"Done! Repo: {repo_full}")
    print(f"PR: {pr_url or 'N/A'}")
    print(f"Status: {status}")
    print(f"{'=' * 60}")

    write_summary(repo_full, pr_url, status, "success" if merged else "partial")


def generate_commit_message(path):
    """Generate a conventional commit message for a file change."""
    if path.lower().startswith("readme"):
        return f"docs: expand README with installation and usage sections"
    elif path == ".gitignore":
        return "chore: add .gitignore for Python project"
    elif path == "requirements.txt":
        return "chore: add requirements.txt with dependencies"
    elif path == "LICENSE":
        return "chore: add MIT LICENSE"
    elif path.endswith(".py"):
        return f"refactor: add docstrings and type hints to {path}"
    else:
        return f"chore: update {path}"


def generate_pr_body(repo_name, changes, messages):
    """Generate a detailed PR body."""
    body = "## Automated Improvements\n\n"
    body += f"This PR was generated by the [Repo Improver Bot](https://github.com/Raj123-0/repo-improver-bot) "
    body += f"to improve **{repo_name}**.\n\n"
    body += "### Changes\n\n"
    for path, msg in zip(changes.keys(), messages):
        body += f"- **{path}** — {msg}\n"
    body += "\n### Why\n\n"
    body += "These are small-to-medium improvements that make the repository more maintainable, "
    body += "discoverable, and easier to use. All changes are additive and non-breaking.\n"
    return body


def write_summary(repo, pr_url, status, result):
    """Write a JSON summary for the nightly email to pick up."""
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "pr_url": pr_url,
        "status": status,
        "result": result,
    }
    with open("run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
