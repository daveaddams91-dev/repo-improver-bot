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
  - Automatic failover across Google Gemini, Mistral/Codestral, and OpenRouter.
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

## Configuration

The bot is configured via GitHub Actions secrets or environment variables:

| Variable | Description |
|---|---|
| `GH_TOKEN` / `REPO_IMPROVER_TOKEN` | GitHub Personal Access Token (`repo`, `workflow`) |
| `PROVIDER_KEYS` | Optional comma-separated keys (`key1,key2,key3`) for all LLM providers |
| `LLM_API_KEY` | Provider 1 API Key (Google Gemini) |
| `LLM2_API_KEY` | Provider 2 API Key (OpenRouter) |
| `LLM3_API_KEY` | Provider 3 API Key (Mistral AI) |
| `MAX_REPOS_PER_RUN` | Max repos to process per scheduled execution (default: `2`) |
| `TARGET_REPO` | Optional repository name to explicitly target |
| `IMPROVEMENT_MODE` | Optional stage override (`auto`, `tests`, `benchmarks`, `optimization`, `documentation`) |

---

## Running Locally

1. Clone the repository:
   ```bash
   git clone https://github.com/Raj123-0/repo-improver-bot.git
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
