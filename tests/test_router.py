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


def _clear_all_keys(monkeypatch):
    for v in (
        "LLM_API_KEY", "GEMINI_API_KEY", "LLM2_API_KEY", "LLM3_API_KEY", "GROQ_API_KEY",
        "ZAI_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY",
        "ZHIPU_API_KEY", "CEREBRAS_API_KEY", "GITHUB_MODELS_TOKEN", "MODELS_TOKEN",
        "NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "SAMBANOVA_API_KEY", "HF_TOKEN",
        "HUGGINGFACE_API_KEY", "TOGETHER_API_KEY", "LLM7_API_KEY", "OVH_AI_API_KEY",
        "CLOUDFLARE_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
        "PROVIDER_KEYS", "KILO_API_KEY",
    ):
        monkeypatch.delenv(v, raising=False)


def test_init_providers_with_provider_keys(monkeypatch):
    _clear_all_keys(monkeypatch)
    monkeypatch.setenv("PROVIDER_KEYS", "key1,key2,key3,key4,key5")

    router = LLMRouter(config={}, enable_keyless_fallback=False)
    assert len(router.providers) >= 1
    assert os.environ.get("GROQ_API_KEY") == "key1"
    assert os.environ.get("LLM2_API_KEY") == "key2"
    assert os.environ.get("LLM3_API_KEY") == "key3"
    assert os.environ.get("ZAI_API_KEY") == "key4"
    assert os.environ.get("COHERE_API_KEY") == "key5"


def test_gemini_removed(monkeypatch):
    _clear_all_keys(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "legacy-gemini-key")
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-gemini-key")
    router = LLMRouter(config={}, enable_keyless_fallback=False)
    names = [p["name"] for p in router.providers]
    assert not any("Gemini" in n for n in names), names


def test_new_free_providers_activate(monkeypatch):
    _clear_all_keys(monkeypatch)
    monkeypatch.setenv("CEREBRAS_API_KEY", "k")
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setenv("HF_TOKEN", "k")
    monkeypatch.setenv("SAMBANOVA_API_KEY", "k")
    router = LLMRouter(config={}, enable_keyless_fallback=False)
    names = {p["name"] for p in router.providers}
    assert {"Cerebras", "NVIDIA NIM", "Hugging Face", "SambaNova"} <= names, names


def test_cloudflare_requires_account_id(monkeypatch):
    _clear_all_keys(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "k")
    router = LLMRouter(config={}, enable_keyless_fallback=False)
    assert not any(p["name"] == "Cloudflare Workers AI" for p in router.providers)

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    router2 = LLMRouter(config={}, enable_keyless_fallback=False)
    cf = [p for p in router2.providers if p["name"] == "Cloudflare Workers AI"]
    assert cf and "acct123" in cf[0]["endpoint"]


def test_keyless_kilo_fallback(monkeypatch):
    _clear_all_keys(monkeypatch)

    router = LLMRouter(config={}, enable_keyless_fallback=True)
    # Even with ZERO API keys set, Kilo AI is available as fallback!
    assert len(router.providers) == 1
    assert "KiloAI" in router.providers[0]["name"]


def test_parse_json_literal_newlines_in_code():
    """Models often emit multi-line code with raw (unescaped) newlines.

    Regression: this used to fail strict parsing and the whole LLM improvement
    was silently discarded.
    """
    payload = (
        "```json\n{\n"
        '  "improved_code": "def f():\n    return 1\n",\n'
        '  "summary": "ok",\n'
        '  "tests": null\n}\n```'
    )
    res = LLMRouter.parse_json(payload)
    assert res is not None
    assert res["improved_code"] == "def f():\n    return 1\n"


def test_parse_json_literal_tab_in_string():
    payload = '{"improved_code": "x = 1\t\n", "summary": "s"}'
    res = LLMRouter.parse_json(payload)
    assert res is not None
    assert res["improved_code"] == "x = 1\t\n"


def test_parse_json_multiline_with_trailing_comma():
    payload = '{"improved_code": "a = 1\nb = 2\n", "summary": "s",}'
    res = LLMRouter.parse_json(payload)
    assert res is not None
    assert "a = 1" in res["improved_code"]
