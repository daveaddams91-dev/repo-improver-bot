"""Tests for the merge gate and licence-aware packaging metadata.

The bot previously created a PR and squash-merged it five seconds later with no
review and no waiting for CI, on a two-hour cron. It also generated
pyproject.toml claiming MIT on every repo, including Apache-2.0 ones.
"""
import importlib
import os
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def bot(monkeypatch):
    """Reload improve with a controlled merge configuration."""
    def _load(auto_merge="", merge_without_ci=""):
        monkeypatch.setenv("BOT_AUTO_MERGE", auto_merge)
        monkeypatch.setenv("BOT_MERGE_WITHOUT_CI", merge_without_ci)
        import improve
        importlib.reload(improve)
        return improve
    return _load


# --------------------------------------------------------------------------
# The default must be the safe one: open a PR, do not merge it.
# --------------------------------------------------------------------------
def test_auto_merge_is_off_by_default(bot):
    m = bot()
    assert m.AUTO_MERGE is False


def test_disabled_merge_makes_no_api_call(bot, monkeypatch):
    m = bot()
    calls = []
    monkeypatch.setattr(m, "gh_put", lambda *a, **k: calls.append(a) or {"merged": True})
    assert m.merge_pr("o", "r", 1) is False
    assert calls == [], "must not call the merge API when auto-merge is off"


@pytest.mark.parametrize(
    "state,summary",
    [("failing", "one failed"), ("pending", "still running"), ("unknown", "unreadable")],
)
def test_refuses_to_merge_unless_green(bot, monkeypatch, state, summary):
    m = bot(auto_merge="true")
    monkeypatch.setattr(m, "wait_for_checks", lambda *a, **k: (state, summary))
    calls = []
    monkeypatch.setattr(m, "gh_put", lambda *a, **k: calls.append(a) or {"merged": True})
    assert m.merge_pr("o", "r", 1) is False
    assert calls == []


def test_refuses_when_repo_has_no_ci(bot, monkeypatch):
    m = bot(auto_merge="true")
    monkeypatch.setattr(m, "wait_for_checks", lambda *a, **k: ("none", "no checks"))
    calls = []
    monkeypatch.setattr(m, "gh_put", lambda *a, **k: calls.append(a) or {"merged": True})
    assert m.merge_pr("o", "r", 1) is False
    assert calls == []


def test_merges_when_green_and_opted_in(bot, monkeypatch):
    m = bot(auto_merge="true")
    monkeypatch.setattr(m, "wait_for_checks", lambda *a, **k: ("passing", "ok"))
    monkeypatch.setattr(m, "gh_put", lambda *a, **k: {"merged": True})
    assert m.merge_pr("o", "r", 1) is True


def test_merges_without_ci_only_with_explicit_override(bot, monkeypatch):
    m = bot(auto_merge="true", merge_without_ci="true")
    monkeypatch.setattr(m, "wait_for_checks", lambda *a, **k: ("none", "no checks"))
    monkeypatch.setattr(m, "gh_put", lambda *a, **k: {"merged": True})
    assert m.merge_pr("o", "r", 1) is True


def test_merge_method_is_not_hardcoded(bot, monkeypatch):
    m = bot()
    monkeypatch.setenv("BOT_MERGE_METHOD", "rebase")
    importlib.reload(m)
    assert m.MERGE_METHOD == "rebase"


def test_merge_request_note_is_written(bot, tmp_path, monkeypatch):
    m = bot()
    monkeypatch.chdir(tmp_path)
    m.write_merge_request("owner/repo", "https://example/pr/1", 1, "checks running")
    note = (tmp_path / "MERGE_REQUEST.md").read_text(encoding="utf-8")
    assert "https://example/pr/1" in note
    assert "owner/repo" in note


# --------------------------------------------------------------------------
# Packaging metadata must reflect the real licence.
# --------------------------------------------------------------------------
def _pyproject(m, spdx, name="demo", desc="d"):
    return m.generate_pyproject(
        name,
        {"name": name, "license": ({"spdx_id": spdx} if spdx else None),
         "owner": {"login": "owner"}, "description": desc},
        ["demo.py"],
    )


def test_mit_repo_gets_mit_licence(bot):
    out = _pyproject(bot(), "MIT")
    assert tomllib.loads(out)["project"]["license"] == {"text": "MIT"}


def test_apache_repo_does_not_claim_mit(bot):
    out = _pyproject(bot(), "Apache-2.0", "docutrust", "verifiable credentials")
    data = tomllib.loads(out)
    assert data["project"]["license"] == {"text": "Apache-2.0"}
    assert "MIT" not in out


def test_unknown_licence_omits_the_field(bot):
    out = _pyproject(bot(), None)
    assert "license" not in tomllib.loads(out)["project"]


@pytest.mark.parametrize("spdx", ["MIT", "Apache-2.0", "GPL-3.0", "BSD-3-Clause", None])
def test_generated_pyproject_is_valid_toml(bot, spdx):
    tomllib.loads(_pyproject(bot(), spdx))


def test_no_mathematics_classifier_on_a_crypto_repo(bot):
    out = _pyproject(bot(), "Apache-2.0", "docutrust",
                     "verifiable credentials zero-knowledge agent identity")
    assert "Mathematics" not in out
