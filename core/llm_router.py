"""Resilient Multi-Provider LLM Router with Fast Failover and JSON Repair.

Supports Google Gemini, Mistral AI, and OpenRouter with zero long-sleep stalls
and robust schema-validated responses.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Any

CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "llm-config.json"
)


def load_config() -> dict[str, Any]:
    """Load configuration from llm-config.json, if present."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: could not read {CONFIG_FILE}: {e}")
    return {}


class LLMRouter:
    """Manages multi-provider LLM calls with instant failover."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config if config is not None else load_config()
        self.providers: list[dict[str, Any]] = self._init_providers()

    def _init_providers(self) -> list[dict[str, Any]]:
        # Check combined PROVIDER_KEYS first if individual keys aren't provided
        pk = os.environ.get("PROVIDER_KEYS", "").strip()
        if pk and not os.environ.get("LLM_API_KEY"):
            parts = [p.strip() for p in pk.split(",") if p.strip()]
            for idx, key in enumerate(parts[:3]):
                var_name = "LLM_API_KEY" if idx == 0 else f"LLM{idx + 1}_API_KEY"
                if not os.environ.get(var_name):
                    os.environ[var_name] = key

        providers = []

        # Provider 1 (Default: Google Gemini OpenAI-compatible)
        p1 = self._build_provider(
            prefix="LLM_",
            default_base="https://generativelanguage.googleapis.com/v1beta/openai",
            default_models=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"],
        )
        if p1:
            providers.append(p1)

        # Provider 2 (Default: Mistral AI)
        p2 = self._build_provider(
            prefix="LLM3_",
            default_base="https://api.mistral.ai/v1",
            default_models=["codestral-latest", "mistral-small-latest", "mistral-large-latest"],
        )
        if p2:
            providers.append(p2)

        # Provider 3 (Default: OpenRouter)
        p3 = self._build_provider(
            prefix="LLM2_",
            default_base="https://openrouter.ai/api/v1",
            default_models=[
                "qwen/qwen-2.5-coder-32b-instruct",
                "deepseek/deepseek-chat",
                "meta-llama/llama-3.3-70b-instruct",
                "z-ai/glm-5.2:free",
                "cohere/north-mini-code:free",
            ],
        )
        if p3:
            providers.append(p3)

        return providers

    def _build_provider(
        self,
        prefix: str,
        default_base: str,
        default_models: list[str]
    ) -> dict[str, Any] | None:
        key = os.environ.get(f"{prefix}API_KEY")
        if not key:
            return None

        base = os.environ.get(f"{prefix}BASE_URL") or self.config.get(f"{prefix}BASE_URL") or default_base
        raw_models = os.environ.get(f"{prefix}MODEL") or self.config.get(f"{prefix}MODEL") or ""
        models = [m.strip() for m in raw_models.split(",") if m.strip()] if raw_models else default_models

        clean_base = base.rstrip("/")
        return {
            "name": prefix.rstrip("_"),
            "base": clean_base,
            "endpoint": f"{clean_base}/chat/completions",
            "token": key,
            "models": list(models),
            "discovered": False,
        }

    def call_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 16000
    ) -> str | None:
        """Call LLM providers in sequence with fast failover on rate-limiting."""
        if not self.providers:
            print("  [LLMRouter] No LLM providers configured with valid API keys.")
            return None

        for provider in self.providers:
            endpoint = provider["endpoint"]
            token = provider["token"]
            models = list(provider["models"])

            for model in models:
                payload = json.dumps({
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }).encode("utf-8")

                # Try at most 2 quick attempts per model (no long sleep stalls!)
                for attempt in range(2):
                    req = urllib.request.Request(
                        endpoint,
                        data=payload,
                        method="POST",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "User-Agent": "repo-improver-bot/5.0",
                        },
                    )

                    try:
                        with urllib.request.urlopen(req, timeout=90) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                        content = data["choices"][0]["message"]["content"]
                        if content:
                            print(f"  [LLMRouter] Responded via {provider['name']} ({model})")
                            return content

                    except urllib.error.HTTPError as e:
                        err_body = ""
                        try:
                            err_body = e.read().decode("utf-8", errors="ignore")[:300]
                        except Exception:
                            pass

                        # 429 Rate Limit Handling
                        if e.code == 429:
                            if "quota" in err_body.lower() or "billing" in err_body.lower():
                                print(f"  [LLMRouter] {provider['name']} ({model}) daily quota exhausted. Moving to next provider.")
                                break  # Break model loop, jump to next provider immediately!

                            print(f"  [LLMRouter] {model} rate-limited (429). Attempt {attempt + 1}/2.")
                            if attempt == 0:
                                time.sleep(3)  # Short 3-second jitter only
                                continue
                            # Fast failover to next model in fallback list
                            break

                        # 503 Overload / 500 Server Error
                        if e.code in (500, 502, 503, 504):
                            print(f"  [LLMRouter] {model} service unavailable ({e.code}). Attempt {attempt + 1}/2.")
                            if attempt == 0:
                                time.sleep(2)
                                continue
                            break

                        # 404 Model Not Found / Retired
                        if e.code == 404:
                            print(f"  [LLMRouter] {model} returned 404 Not Found.")
                            break

                        print(f"  [LLMRouter] {model} failed: HTTP {e.code}: {err_body[:120]}")
                        break

                    except Exception as e:
                        print(f"  [LLMRouter] {model} connection error: {e}")
                        break

        return None

    @staticmethod
    def parse_json(content: str | None) -> dict[str, Any] | None:
        """Extract and parse a JSON object from model output with syntax repair."""
        if not content or not content.strip():
            return None

        text = content.strip()

        # 1. Strip markdown fences if present
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # 2. Extract outermost JSON bounds
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        json_str = text[start:end + 1]

        # First direct parse attempt
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Repair 1: Fix invalid backslashes (e.g. raw \d, \s, \w, \b in code strings)
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Repair 2: Fix trailing commas before closing braces/brackets
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        return None
