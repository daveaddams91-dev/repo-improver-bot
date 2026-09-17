"""Unit tests for LLMRouter and JSON parsing."""

import os
import json
from core.llm_router import LLMRouter


def test_parse_json_clean():
    payload = '{"improved_code": "print(1)", "summary": "clean", "tests": null}'
    res = LLMRouter.parse_json(payload)
    assert res is not None
    assert res["improved_code"] == "print(1)"
    assert res["summary"] == "clean"


def test_parse_json_fenced():
    payload = """```json
{
  "improved_code": "def foo(): pass",
  "summary": "added func",
  "tests": "def test_foo(): pass"
}
```"""
    res = LLMRouter.parse_json(payload)
    assert res is not None
    assert "def foo(): pass" in res["improved_code"]


def test_parse_json_with_reasoning_preamble():
    payload = """Thinking Process:
1. I will write an improved module.
2. Here is the JSON output:
{"improved_code": "def run(): return 42", "summary": "returns 42", "tests": null}
Final thoughts: Done!"""
    res = LLMRouter.parse_json(payload)
    assert res is not None
    assert res["improved_code"] == "def run(): return 42"


def test_parse_json_raw_backslashes():
    raw = '{"improved_code": "re.findall(\'\\d+\', text)", "summary": "regex fix"}'
    res = LLMRouter.parse_json(raw)
    assert res is not None
    assert "\\d+" in res["improved_code"]


def test_parse_json_trailing_comma():
    raw = '{"improved_code": "x = 1", "summary": "test",}'
    res = LLMRouter.parse_json(raw)
    assert res is not None
    assert res["improved_code"] == "x = 1"


def test_parse_json_empty_or_invalid():
    assert LLMRouter.parse_json(None) is None
    assert LLMRouter.parse_json("") is None
    assert LLMRouter.parse_json("not a json string at all") is None


def test_init_providers_with_provider_keys(monkeypatch):
    monkeypatch.setenv("PROVIDER_KEYS", "key1,key2,key3,key4")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM2_API_KEY", raising=False)
    monkeypatch.delenv("LLM3_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    router = LLMRouter(config={}, enable_keyless_fallback=False)
    assert len(router.providers) >= 1
    assert os.environ.get("LLM_API_KEY") == "key1"
    assert os.environ.get("LLM2_API_KEY") == "key2"
    assert os.environ.get("LLM3_API_KEY") == "key3"
    assert os.environ.get("GROQ_API_KEY") == "key4"


def test_keyless_kilo_fallback(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM2_API_KEY", raising=False)
    monkeypatch.delenv("LLM3_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("PROVIDER_KEYS", raising=False)

    router = LLMRouter(config={}, enable_keyless_fallback=True)
    # Even with ZERO API keys set, Kilo AI is available as fallback!
    assert len(router.providers) == 1
    assert "KiloAI" in router.providers[0]["name"]
