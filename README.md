# Repo Improver Bot (v5 Autonomous Engine)

An autonomous GitHub repository engineering bot that continuously analyzes, improves, and elevates repositories across your account with genuine, domain-aware enhancements.

## Key Features

- **Domain-Aware Engineering**: Rather than applying generic boilerplate, the bot classifies repositories into specialized domains:
  - **Mathematical Constant & OEIS Engines**: Accuracy verification against known OEIS digits, precision optimization, automated benchmark suites (`benchmarks/bench_precision.py`), and mathematical documentation.
  - **Systems, Languages & Compilers**: Parser/lexer testing, tokenization throughput benchmarks, syntax error diagnostics, and type annotations.
  - **Scientific Simulation, Physics & Cryptography**: Numerical stability, vectorization with NumPy, constant-time crypto checks, and invariant-testing unit suites.
  - **Desktop Applications & Utilities**: Headless unit test decoupling, CLI enhancements, and platform-safe path/file operations.
- **Capability Ladder Progression**:
  1. `L1 Hygiene`: Real `.gitignore`, packaging, license, and AST cleanup.
  2. `L2 Tests`: Comprehensive behavioral unit tests with real assertions and ground truth.
  3. `L3 Benchmarks`: Automated performance and precision benchmark suites.
  4. `L4 Optimization`: Algorithmic acceleration, vectorization, caching, and type hardening.
  5. `L5 Documentation`: Accurate, domain-specific technical documentation and usage guides.
- **Resilient Multi-Provider LLM Router**:
  - Automatic failover across 15 free-tier providers (Groq, Cerebras, NVIDIA NIM, GitHub Models, Mistral, OpenRouter, and more).
  - Zero-stall error handling: eliminates long sleep stalls on rate-limiting (429/503).
  - Robust JSON parsing with syntax repair.
- **Sandboxed Verification Gate**:
  - Pre-validates all generated code in an isolated temporary sandbox with `pytest`.
  - Automated self-repair: feeds test failure outputs back to the model for correction.
  - Broken code is never committed or merged.
- **Persistent State Ledger (`repo_registry.json`)**:
  - Tracks every repository's domain, completion stages, and update history to prevent repetition and ensure high-frequency progression.
- **Keep-Alive Heartbeat**:
  - Automatically updates `LAST_RUN.md` on every scheduled cycle to ensure GitHub never disables scheduled Actions workflows.

---

## Architecture Overview

```
repo-improver-bot/
├── .github/workflows/
│   └── improve-repos.yml      # 24/7 scheduled GitHub Action (runs every 2 hours)
├── core/
│   ├── registry.py            # Persistent state ledger & domain classifier
│   ├── llm_router.py          # Fast-failover multi-provider LLM client
│   ├── verifier.py            # AST validation & sandboxed pytest runner
│   └── domain_improvers.py    # Specialized tests, benchmarks, and docs generators
├── tests/                     # Test suite for the bot itself
│   ├── test_router.py
│   ├── test_registry.py
│   ├── test_verifier.py
│   └── test_domain_improvers.py
├── improve.py                 # GitHub REST API plumbing & AST transformations
├── improve_llm.py             # Main orchestration engine
├── llm-config.json            # Model and endpoint configuration
├── repo_registry.json         # State ledger (auto-updated on runs)
└── LAST_RUN.md                # 60-day keep-alive heartbeat
```

---

## Supported LLM Providers & Free Tiers

The bot integrates free-tier APIs curated from [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis), cascading in order:

| Provider | Env Secret | Notable Models | Free Rate Limits |
|---|---|---|---|
| **Groq** | `GROQ_API_KEY` | `openai/gpt-oss-120b` | 30 RPM, ~1,000–14,400 req/day |
| **Cerebras** | `CEREBRAS_API_KEY` | `gpt-oss-120b`, `llama-3.3-70b` | 30 RPM, ~14,400 req/day |
| **GitHub Models** | `GITHUB_MODELS_TOKEN` | `openai/gpt-4o-mini`, `meta/Llama-3.3-70B-Instruct` | 10–15 RPM, 50–150 req/day |
| **NVIDIA NIM** | `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` | ~40 RPM, no daily cap |
| **Mistral AI** | `LLM3_API_KEY` / `MISTRAL_API_KEY` | `codestral-latest`, `mistral-small-latest` | ~1 RPS, 500K tokens/min |
| **SambaNova** | `SAMBANOVA_API_KEY` | `Meta-Llama-3.3-70B-Instruct` | 20 RPM, 20 req/day |
| **OpenRouter** | `LLM2_API_KEY` / `OPENROUTER_API_KEY` | `:free` routes | 20 RPM, 50–1,000 req/day |
| **Hugging Face** | `HF_TOKEN` | `Qwen/Qwen2.5-72B-Instruct` | monthly inference credits |
| **Together AI** | `TOGETHER_API_KEY` | selected `$0` models | free model tier |
| **Z.AI (Zhipu)** | `ZAI_API_KEY` / `ZHIPU_API_KEY` | `glm-4.7-flash`, `glm-4.5-flash` | ~1,000 req/day |
| **LLM7.io** | `LLM7_API_KEY` *(optional)* | `gpt-oss-120b` | ~30–120 RPM |
| **OVHcloud AI** | `OVH_AI_API_KEY` *(optional)* | `Meta-Llama-3_3-70B-Instruct` | anonymous ~2 RPM |
| **Cohere** | `COHERE_API_KEY` | `command-r-plus`, `command-r` | 20 RPM, 1,000 calls/month |
| **Cloudflare Workers AI** | `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 10,000 neurons/day |
| **Kilo AI** | *(None required / Keyless)* | `kilo-auto/free` | 200 req/hr per IP (zero key needed!) |

Each provider activates **only when its secret is present**, so you can add keys one at a time. More keys = more combined headroom before any single rate limit bites. Model IDs are overridable in `llm-config.json` (or via a `<PREFIX>_MODEL` env var) as providers rotate their catalogs.

> [!TIP]
> **Zero Quota Exhaustion**: Even if all personal API keys hit their daily limit, the bot seamlessly cascades to Kilo AI's free model pool so autonomous scheduled runs never stop!

## Configuration

| Variable | Description |
|---|---|
| `GH_TOKEN` / `REPO_IMPROVER_TOKEN` | GitHub Personal Access Token (`repo`, `workflow`) |
| `PROVIDER_KEYS` | Optional comma-separated keys, positional order (`groq,openrouter,mistral,zai,cohere`) |
| `GROQ_API_KEY` | Groq API Key |
| `CEREBRAS_API_KEY` | Cerebras API Key |
| `GITHUB_MODELS_TOKEN` | GitHub Models token (a GitHub PAT works) |
| `NVIDIA_API_KEY` | NVIDIA NIM API Key |
| `LLM3_API_KEY` / `MISTRAL_API_KEY` | Mistral AI API Key |
| `SAMBANOVA_API_KEY` | SambaNova API Key |
| `LLM2_API_KEY` / `OPENROUTER_API_KEY` | OpenRouter API Key |
| `HF_TOKEN` / `HUGGINGFACE_API_KEY` | Hugging Face token |
| `TOGETHER_API_KEY` | Together AI API Key |
| `ZAI_API_KEY` / `ZHIPU_API_KEY` | Z.AI GLM API Key |
| `LLM7_API_KEY` | LLM7.io token (optional — works anonymously too) |
| `OVH_AI_API_KEY` | OVHcloud AI Endpoints key (optional) |
| `COHERE_API_KEY` | Cohere API Key |
| `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Workers AI |
| `MAX_REPOS_PER_RUN` | Max repos to process per scheduled execution (default: `2`) |
| `TARGET_REPO` | Optional repository name to explicitly target |
| `IMPROVEMENT_MODE` | Optional stage override (`auto`, `tests`, `benchmarks`, `optimization`, `documentation`) |

---

## Running Locally

1. Clone the repository:
   ```bash
   git clone https://github.com/rajveersinh-is-dev/repo-improver-bot.git
   cd repo-improver-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt  # requests, pytest, gmpy2, mpmath, numpy
   ```

3. Run the automated test suite:
   ```bash
   pytest tests/ -v
   ```

4. Run a single improvement cycle:
   ```bash
   python improve_llm.py
   ```

---

## License

MIT License. Copyright (c) 2026 Raj123-0.
