# Contributing to NowLens AI

Thanks for your interest in improving NowLens. This guide covers how to set up, the quality bar, and how changes are reviewed.

## Development setup

Requires Python 3.11+.

```bash
git clone <repo-url> && cd nowlens-ai
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install        # optional but recommended
```

Optional extras: `".[rerank]"` (cross-encoder), `".[render]"` (JS rendering), `".[worker]"` (arq queue), `".[langfuse]"` (tracing).

## The quality bar

Every change must pass the same gate CI runs. Run it locally before opening a PR:

```bash
make check     # ruff + mypy + pytest
```

Individually:

```bash
make format      # black + ruff --fix (apply formatting/auto-fixes)
make lint        # ruff check + black --check
make typecheck   # mypy src  (strict; must stay green)
make test        # pytest    (fully offline; no external services)
```

Standards:

- **Formatting & lint:** `black` and `ruff`, line length 100. Keep imports sorted (ruff handles this).
- **Types:** `mypy` runs in strict mode over `src/`. New code should be fully typed; don't add `# type: ignore` without a reason.
- **Tests:** add or update tests for any behaviour change. The suite must run without network access, Qdrant, Postgres, Ollama, or Groq — use the in-memory fakes in `tests/conftest.py`. Async tests are auto-handled (`asyncio_mode = auto`).
- **No secrets** in code, tests, or fixtures.

## Architectural conventions

- Depend on the provider-agnostic interfaces in `nowlens.llm.base`, not on a concrete vendor.
- All SQL lives in `nowlens.db.repositories`.
- All configuration goes through `nowlens.core.config` (no direct `os.environ`).
- Raise typed exceptions from `nowlens.core.exceptions` so the API renders a consistent error envelope.
- Keep agent nodes thin: assemble a prompt, call the LLM, write structured state back.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before making structural changes.

## Commits and pull requests

- Write clear, imperative commit messages (e.g. "Add cross-encoder reranker option"). Conventional Commit prefixes (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`) are welcome but not required.
- Keep PRs focused. Describe what changed and why; link any related issue.
- Update docs (`docs/`, `README.md`, `.env.example`) when behaviour or configuration changes.
- Add a `CHANGELOG.md` entry under "Unreleased" for user-facing changes.

## Adding things

- **A new LLM/embedding backend:** implement `LLMProvider` / `EmbeddingProvider` and register it in `llm.factory`.
- **A new specialist agent:** add the node function, register it in `agents.graph._SPECIALISTS`, and extend the router vocabulary in `agents.base`.
- **A new ServiceNow domain:** extend the registry in `core.domains` (and add a quick test).

## Reporting bugs and proposing features

Open an issue with a minimal reproduction (for bugs) or a clear problem statement and proposed approach (for features). Security issues should follow [SECURITY.md](SECURITY.md) instead of a public issue.

## License

By contributing, you agree that your contributions are licensed under the project's [Apache-2.0](LICENSE) license.
