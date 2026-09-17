"""Repo Registry and Domain Classifier.

Tracks repository maturity levels across runs and selects the highest-priority
repository and task for high-frequency, non-repetitive improvements.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any

REGISTRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "repo_registry.json"
)

# Domain Classifications
DOMAIN_MATH_CONSTANT = "math_constant_oeis"
DOMAIN_SYSTEMS_COMPILER = "systems_compiler"
DOMAIN_PHYSICS_CRYPTO = "physics_simulation_crypto"
DOMAIN_DESKTOP_UTILITY = "desktop_app_utility"
DOMAIN_GENERAL_PYTHON = "general_python"

# Progressive Improvement Stages
STAGES = [
    "hygiene",         # L1: .gitignore, requirements, pyproject, basic lint/formatting
    "tests",           # L2: Real behavioral unit tests with verified assertions
    "benchmarks",      # L3: Automated performance & precision benchmark suites
    "optimization",    # L4: Algorithmic speedups, vectorization, caching, type hardening
    "documentation",   # L5: Domain-accurate README with real formulas/APIs/examples
]

MATH_CONSTANT_KEYWORDS = (
    "constant", "ratio", "number", "oeis", "precision", "digits",
    "chudnovsky", "lemniscate", "zeta", "feigenbaum", "parabolic",
    "supergolden", "theodorus", "golomb", "dickman", "sierpinski",
    "silver", "robbins", "ramanujan", "soldner", "plastic", "omega",
    "meissel", "mertens", "lieb", "laplace", "khinchin", "gompertz",
    "golden", "glaisher", "kinkelin", "gelfond", "gauss", "euler",
    "catalan", "erdos", "borwein", "dottie", "cahen", "brun", "artin", "apery"
)

SYSTEMS_KEYWORDS = (
    "compiler", "interpreter", "bytecode", "lexer", "parser", "vm",
    "numlang", "grammar", "ast", "codec", "tether-codec", "instruction"
)

PHYSICS_CRYPTO_KEYWORDS = (
    "tokamak", "plasma", "crypt", "crypto", "cipher", "argon2", "pbkdf2",
    "lattice", "reduction", "lll", "avalanche", "dynamics", "graph",
    "erosion", "simulation", "physics", "equilibrium", "dose"
)

DESKTOP_UTILITY_KEYWORDS = (
    "desktop", "gui", "tkinter", "customtkinter", "cookie", "toolkit",
    "scholarly", "doubt", "ocr", "app"
)


def detect_domain(
    repo_name: str,
    description: str = "",
    file_paths: list[str] | None = None,
    readme_text: str = ""
) -> str:
    """Classifies a repository into a functional domain to guide tailored improvements."""
    name_lower = repo_name.lower().replace("_", "-")
    desc_lower = (description or "").lower()
    readme_lower = (readme_text or "").lower()
    combined_text = f"{name_lower} {desc_lower} {readme_lower[:500]}"

    # Check desktop & GUI utilities first (e.g. StegoCrypt-Desktop)
    if any(k in name_lower for k in ("-desktop", "desktop", "gui", "cookie-manager", "dev-toolkit", "scholarly")):
        return DOMAIN_DESKTOP_UTILITY
    if any(k in combined_text for k in DESKTOP_UTILITY_KEYWORDS) and "desktop" in name_lower:
        return DOMAIN_DESKTOP_UTILITY

    # Check systems & compilers
    if any(k in name_lower for k in ("numlang", "tether-codec")):
        return DOMAIN_SYSTEMS_COMPILER
    if any(k in combined_text for k in SYSTEMS_KEYWORDS):
        return DOMAIN_SYSTEMS_COMPILER

    # Check physics, simulation & cryptography (including RationalLLL)
    if any(k in name_lower for k in (
        "tokamak", "aegis", "rationallll", "rational", "avalanche", "terrain", "certified-dose"
    )):
        return DOMAIN_PHYSICS_CRYPTO
    if any(k in combined_text for k in PHYSICS_CRYPTO_KEYWORDS) and "constant" not in name_lower:
        return DOMAIN_PHYSICS_CRYPTO

    # Check math constant repos (segments or specific keywords)
    math_tokens = {
        "constant", "ratio", "supergolden", "number", "oeis", "precision", "digits",
        "chudnovsky", "lemniscate", "zeta", "feigenbaum", "parabolic",
        "theodorus", "golomb", "dickman", "sierpinski", "silver", "robbins",
        "ramanujan", "soldner", "plastic", "omega", "meissel", "mertens",
        "lieb", "laplace", "khinchin", "gompertz", "golden", "glaisher",
        "kinkelin", "gelfond", "gauss", "euler", "catalan", "erdos",
        "borwein", "dottie", "cahen", "brun", "artin", "apery"
    }
    name_segments = set(re.split(r"[-_]+", name_lower))
    if any(k in name_segments for k in math_tokens):
        return DOMAIN_MATH_CONSTANT
    if any(name_lower.endswith(f"-{k}") or name_lower.startswith(f"{k}-") for k in ("constant", "ratio", "number")):
        return DOMAIN_MATH_CONSTANT
    if any(k in name_lower for k in (
        "chudnovsky", "lemniscate", "zeta", "feigenbaum", "parabolic",
        "theodorus", "golomb", "dickman", "sierpinski", "robbins",
        "ramanujan", "soldner", "plastic", "meissel", "mertens",
        "lieb", "khinchin", "gompertz", "glaisher", "kinkelin",
        "gelfond", "catalan", "erdos", "borwein", "dottie", "cahen", "brun"
    )):
        return DOMAIN_MATH_CONSTANT
    if "oeis" in combined_text or ("constant" in combined_text and "digits" in combined_text):
        return DOMAIN_MATH_CONSTANT

    return DOMAIN_GENERAL_PYTHON


class RepoRegistry:
    """Manages the persistent registry of repositories and their improvement stages."""

    def __init__(self, registry_path: str = REGISTRY_FILE):
        self.path = registry_path
        self.data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: could not load registry from {self.path}: {e}")
        return {}

    def save(self) -> None:
        """Atomically persist registry data to disk."""
        tmp_path = self.path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, sort_keys=True)
            os.replace(tmp_path, self.path)
        except Exception as e:
            print(f"Error saving registry: {e}")

    def get_repo(self, repo_name: str) -> dict[str, Any]:
        """Return or initialize registry entry for a repository."""
        if repo_name not in self.data:
            self.data[repo_name] = {
                "domain": DOMAIN_GENERAL_PYTHON,
                "stages_completed": [],
                "last_improved_at": None,
                "improvements_count": 0,
                "pr_history": [],
            }
        return self.data[repo_name]

    def update_repo_info(
        self,
        repo_name: str,
        domain: str,
        description: str = "",
        language: str = "Python"
    ) -> None:
        """Update static repo characteristics."""
        entry = self.get_repo(repo_name)
        entry["domain"] = domain
        entry["description"] = description
        entry["language"] = language

    def record_stage(
        self,
        repo_name: str,
        stage: str,
        pr_url: str | None = None,
        summary: str = ""
    ) -> None:
        """Record successful completion of an improvement stage."""
        entry = self.get_repo(repo_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        entry["last_improved_at"] = now_iso
        entry["improvements_count"] = entry.get("improvements_count", 0) + 1

        if stage not in entry.setdefault("stages_completed", []):
            entry["stages_completed"].append(stage)

        pr_record = {
            "stage": stage,
            "timestamp": now_iso,
            "pr_url": pr_url,
            "summary": summary,
        }
        entry.setdefault("pr_history", []).append(pr_record)
        # Keep PR history bounded
        entry["pr_history"] = entry["pr_history"][-20:]
        self.save()

    def select_candidate(
        self,
        eligible_repos: list[dict[str, Any]],
        target_name: str | None = None,
        mode_override: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """Selects the best repo and target improvement stage for this run.

        Priority formula balances:
        1. Repos with the fewest completed capability stages.
        2. Repos that have not been touched recently.
        3. Fair round-robin rotation across all repositories.
        """
        if not eligible_repos:
            return None, "hygiene"

        now = datetime.now(timezone.utc)

        # 1. Manual target selection
        if target_name:
            clean_target = target_name.strip().lower()
            matched = [
                r for r in eligible_repos
                if r["name"].lower() == clean_target or r.get("full_name", "").lower() == clean_target
            ]
            if matched:
                repo = matched[0]
                entry = self.get_repo(repo["name"])
                stage = mode_override if mode_override and mode_override != "auto" else self._next_stage(entry)
                return repo, stage

        # 2. Score candidate repositories
        scored: list[tuple[float, dict[str, Any], str]] = []
        for repo in eligible_repos:
            name = repo["name"]
            entry = self.get_repo(name)
            completed = entry.get("stages_completed", [])
            last_ts = entry.get("last_improved_at")

            # Next stage
            if mode_override and mode_override != "auto" and mode_override in STAGES:
                next_stage = mode_override
            else:
                next_stage = self._next_stage(entry)

            # Hours since last improvement by this bot
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts)
                    hours_since_improved = (now - last_dt).total_seconds() / 3600.0
                except Exception:
                    hours_since_improved = 168.0
            else:
                hours_since_improved = 999.0

            # Cooldown check: if repo was improved in last 4 hours, defer it unless all repos are recent
            cooldown_penalty = 0.0
            if hours_since_improved < 4.0:
                cooldown_penalty = 100.0

            # Maturity score: repos that have not completed all stages get priority
            stages_remaining = len(STAGES) - len(completed)
            # Freshness score based on GitHub pushed_at
            pushed_at = repo.get("pushed_at", "")
            try:
                pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_since_push = (now - pushed_dt).total_seconds() / 86400.0
            except Exception:
                days_since_push = 30.0

            # Composite Priority Score (Higher is better)
            score = (
                (stages_remaining * 25.0)
                + min(hours_since_improved, 168.0) * 0.5
                + min(days_since_push, 30.0) * 0.2
                - cooldown_penalty
            )
            scored.append((score, repo, next_stage))

        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            best = scored[0]
            return best[1], best[2]

        return eligible_repos[0], "hygiene"

    def _next_stage(self, entry: dict[str, Any]) -> str:
        """Determines the next uncompleted stage on the capability ladder."""
        completed = set(entry.get("stages_completed", []))
        for stage in STAGES:
            if stage not in completed:
                return stage
        # If all stages completed, cycle back into iterative optimization
        return "optimization"
