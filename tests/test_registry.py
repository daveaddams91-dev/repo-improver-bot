"""Unit tests for RepoRegistry and Domain Classification."""

import os
import tempfile
from core.registry import (
    RepoRegistry,
    detect_domain,
    DOMAIN_MATH_CONSTANT,
    DOMAIN_SYSTEMS_COMPILER,
    DOMAIN_PHYSICS_CRYPTO,
    DOMAIN_DESKTOP_UTILITY,
    DOMAIN_GENERAL_PYTHON,
)


def test_detect_domain_math():
    assert detect_domain("Universal-Parabolic-Constant") == DOMAIN_MATH_CONSTANT
    assert detect_domain("Tribonacci-Constant") == DOMAIN_MATH_CONSTANT
    assert detect_domain("Catalan-s-Constant") == DOMAIN_MATH_CONSTANT
    assert detect_domain("Supergolden-Ratio") == DOMAIN_MATH_CONSTANT
    assert detect_domain("Euler-Number") == DOMAIN_MATH_CONSTANT


def test_detect_domain_systems():
    assert detect_domain("numlang") == DOMAIN_SYSTEMS_COMPILER
    assert detect_domain("tether-codec") == DOMAIN_SYSTEMS_COMPILER
    assert detect_domain("my-custom-parser", description="An AST compiler") == DOMAIN_SYSTEMS_COMPILER


def test_detect_domain_physics_crypto():
    assert detect_domain("Tokamak-Py") == DOMAIN_PHYSICS_CRYPTO
    assert detect_domain("AegisCrypt") == DOMAIN_PHYSICS_CRYPTO
    assert detect_domain("RationalLLL") == DOMAIN_PHYSICS_CRYPTO
    assert detect_domain("avalanche-graph-dynamics") == DOMAIN_PHYSICS_CRYPTO


def test_detect_domain_desktop():
    assert detect_domain("StegoCrypt-Desktop") == DOMAIN_DESKTOP_UTILITY
    assert detect_domain("Cookie-Manager-main") == DOMAIN_DESKTOP_UTILITY


def test_registry_lifecycle_and_selection():
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_file = os.path.join(tmpdir, "test_registry.json")
        reg = RepoRegistry(registry_path=reg_file)

        repos = [
            {"name": "RepoA", "full_name": "user/RepoA", "pushed_at": "2026-08-01T00:00:00Z"},
            {"name": "RepoB", "full_name": "user/RepoB", "pushed_at": "2026-09-01T00:00:00Z"},
        ]

        # First candidate selection
        chosen, stage = reg.select_candidate(repos)
        assert chosen is not None
        assert stage == "hygiene"

        # Record stage for chosen repo
        reg.record_stage(chosen["name"], "hygiene", pr_url="https://github.com/pr/1")

        # Reload from disk
        reg2 = RepoRegistry(registry_path=reg_file)
        assert "hygiene" in reg2.get_repo(chosen["name"])["stages_completed"]

        # Next candidate should now be the other repo or next stage
        next_chosen, next_stage = reg2.select_candidate(repos)
        assert next_chosen is not None
        if next_chosen["name"] == chosen["name"]:
            assert next_stage == "tests"
        else:
            assert next_chosen["name"] != chosen["name"]


def test_registry_target_repo_override():
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_file = os.path.join(tmpdir, "test_registry.json")
        reg = RepoRegistry(registry_path=reg_file)

        repos = [
            {"name": "RepoA", "full_name": "user/RepoA", "pushed_at": "2026-08-01T00:00:00Z"},
            {"name": "RepoB", "full_name": "user/RepoB", "pushed_at": "2026-09-01T00:00:00Z"},
        ]

        chosen, stage = reg.select_candidate(repos, target_name="RepoB", mode_override="benchmarks")
        assert chosen["name"] == "RepoB"
        assert stage == "benchmarks"
