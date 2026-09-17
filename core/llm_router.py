"""Resilient Multi-Provider LLM Router with Fast Failover, Keyless Fallback, and JSON Repair.

Integrates providers from awesome-free-llm-apis:
- Google Gemini (Free tier, 1,500 RPD)
- Groq (Ultra-fast LPU, 1,000 RPD)
- Mistral AI (Codestral & Small, free credits)
- OpenRouter (Free models router & community models)
- Z.AI / Zhipu (GLM-4.7-Flash permanent free tier)
- Cohere (Command-R series free trial)
- Kilo Code (Universal zero-key fallback, 200 req/hr)
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
    """Manages tiered multi-provider LLM calls with instant failover and keyless fallback."""

    def __init__(self, config: dict[str, Any] | None = None, enable_keyless_fallback: bool = True):
        self.config = config if config is not None else load_config()
        self.enable_keyless_fallback = enable_keyless_fallback
        self.providers: list[dict[str, Any]] = self._init_providers()

    def _init_providers(self) -> list[dict[str, Any]]:
        # Map combined PROVIDER_KEYS into individual vars if needed
        pk = os.environ.get("PROVIDER_KEYS", "").strip()
        if pk:
            parts = [p.strip() for p in pk.split(",") if p.strip()]
            var_names = [
                "LLM_API_KEY",      # Gemini
                "LLM2_API_KEY",     # OpenRouter
                "LLM3_API_KEY",     # Mistral
                "GROQ_API_KEY",     # Groq
                "ZAI_API_KEY",      # Z.AI
                "COHERE_API_KEY",   # Cohere
            ]
            for idx, key in enumerate(parts[:len(var_names)]):
                var = var_names[idx]
                if not os.environ.get(var):
                    os.environ[var] = key

        providers = []

        # 1. Google Gemini (15 RPM, 1,500 RPD)
        gemini_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            p = self._build_provider(
                name="Gemini",
                token=gemini_key,
                base_env=os.environ.get("LLM_BASE_URL") or self.config.get("LLM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai",
                model_env=os.environ.get("LLM_MODEL") or self.config.get("LLM_MODEL") or "gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash",
                default_models=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
            )
            if p:
                providers.append(p)

        # 2. Groq (Ultra-fast LPU, 30 RPM, 1,000 RPD)
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            p = self._build_provider(
                name="Groq",
                token=groq_key,
                base_env=os.environ.get("GROQ_BASE_URL") or self.config.get("GROQ_BASE_URL") or "https://api.groq.com/openai/v1",
                model_env=os.environ.get("GROQ_MODEL") or self.config.get("GROQ_MODEL") or "qwen-2.5-coder-32b,llama-3.3-70b-versatile,openai/gpt-oss-120b",
                default_models=["qwen-2.5-coder-32b", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
            )
            if p:
                providers.append(p)

        # 3. Mistral AI (Codestral, 1 RPS, 500K TPM)
        mistral_key = os.environ.get("LLM3_API_KEY") or os.environ.get("MISTRAL_API_KEY")
        if mistral_key:
            p = self._build_provider(
                name="Mistral",
                token=mistral_key,
                base_env=os.environ.get("LLM3_BASE_URL") or self.config.get("LLM3_BASE_URL") or "https://api.mistral.ai/v1",
                model_env=os.environ.get("LLM3_MODEL") or self.config.get("LLM3_MODEL") or "codestral-latest,mistral-small-latest,mistral-large-latest",
                default_models=["codestral-latest", "mistral-small-latest", "mistral-large-latest"],
            )
            if p:
                providers.append(p)

        # 4. OpenRouter (Free models router & community models)
        openrouter_key = os.environ.get("LLM2_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            p = self._build_provider(
                name="OpenRouter",
                token=openrouter_key,
                base_env=os.environ.get("LLM2_BASE_URL") or self.config.get("LLM2_BASE_URL") or "https://openrouter.ai/api/v1",
                model_env=os.environ.get("LLM2_MODEL") or self.config.get("LLM2_MODEL") or "openrouter/free,qwen/qwen-2.5-coder-32b-instruct,deepseek/deepseek-chat",
                default_models=["openrouter/free", "qwen/qwen-2.5-coder-32b-instruct", "deepseek/deepseek-chat"],
            )
            if p:
                providers.append(p)

        # 5. Z.AI / Zhipu GLM (Permanent free tier)
        zai_key = os.environ.get("ZAI_API_KEY") or os.environ.get("ZHIPU_API_KEY")
        if zai_key:
            p = self._build_provider(
                name="Z.AI",
                token=zai_key,
                base_env=os.environ.get("ZAI_BASE_URL") or self.config.get("ZAI_BASE_URL") or "https://api.z.ai/api/paas/v4",
                model_env=os.environ.get("ZAI_MODEL") or self.config.get("ZAI_MODEL") or "glm-4.7-flash,glm-4.5-flash",
                default_models=["glm-4.7-flash", "glm-4.5-flash"],
            )
            if p:
                providers.append(p)

        # 6. Cohere (Command-R series)
        cohere_key = os.environ.get("COHERE_API_KEY")
        if cohere_key:
            p = self._build_provider(
                name="Cohere",
                token=cohere_key,
                base_env=os.environ.get("COHERE_BASE_URL") or self.config.get("COHERE_BASE_URL") or "https://api.cohere.com/v2",
                model_env=os.environ.get("COHERE_MODEL") or self.config.get("COHERE_MODEL") or "command-r-plus,command-r,command-a",
                default_models=["command-r-plus", "command-r", "command-a"],
            )
            if p:
                providers.append(p)

        # 7. Kilo Code (Universal Keyless Public Fallback - 200 req/hr)
        if self.enable_keyless_fallback:
            kilo_base = os.environ.get("KILO_BASE_URL") or self.config.get("KILO_BASE_URL") or "https://api.kilo.ai/api/gateway"
            kilo_raw_models = os.environ.get("KILO_MODEL") or self.config.get("KILO_MODEL") or "kilo-auto/free,nvidia/nemotron-3-ultra-550b-a55b:free,cohere/north-mini-code:free,stepfun/step-3.7-flash:free"
            kilo_models = [m.strip() for m in kilo_raw_models.split(",") if m.strip()]
            providers.append({
                "name": "KiloAI (Keyless Fallback)",
                "base": kilo_base.rstrip("/"),
                "endpoint": f"{kilo_base.rstrip('/')}/chat/completions",
                "token": os.environ.get("KILO_API_KEY", ""),  # Optional: works anonymously without key!
                "models": kilo_models,
            })

        return providers

    def _build_provider(
        self,
        name: str,
        token: str,
        base_env: str,
        model_env: str,
        default_models: list[str]
    ) -> dict[str, Any] | None:
        if not token:
            return None

        clean_base = base_env.rstrip("/")
        models = [m.strip() for m in model_env.split(",") if m.strip()] or default_models
        return {
            "name": name,
            "base": clean_base,
            "endpoint": f"{clean_base}/chat/completions",
            "token": token,
            "models": list(models),
        }

    def call_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 16000
    ) -> str | None:
        """Call LLM providers in sequence with fast failover on rate-limiting."""
        if not self.providers:
            print("  [LLMRouter] No LLM providers configured.")
            return None

        for provider in self.providers:
            endpoint = provider["endpoint"]
            token = provider.get("token", "")
            models = list(provider["models"])

            for model in models:
                payload = json.dumps({
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }).encode("utf-8")

                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "repo-improver-bot/5.0",
                }
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                # Try at most 2 quick attempts per model (no long sleep stalls!)
                for attempt in range(2):
                    req = urllib.request.Request(
                        endpoint,
                        data=payload,
                        method="POST",
                        headers=headers,
                    )

                    try:
                        with urllib.request.urlopen(req, timeout=90) as resp:
                            data = json.loads(resp.read().decode("utf-8"))

                        choice = data.get("choices", [{}])[0]
                        message = choice.get("message", {})
                        content = message.get("content")
                        if not content and message.get("reasoning"):
                            content = message.get("reasoning")

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
                                print(f"  [LLMRouter] {provider['name']} ({model}) quota exhausted. Failing over to next provider.")
                                break  # Jump to next provider immediately!

                            print(f"  [LLMRouter] {model} rate-limited (429). Attempt {attempt + 1}/2.")
                            if attempt == 0:
                                time.sleep(3)  # Short 3-second jitter only
                                continue
                            break

                        # 500/502/503/504 Service Overload
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

        # 2. Extract outermost JSON bounds (safely strips reasoning text preambles)
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
