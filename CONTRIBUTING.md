# Contributing to Symbiote AI

Thanks for your interest in contributing. This document covers everything you
need to get up and running.

## Philosophy

Symbiote AI follows a small-codebase philosophy: the right amount of complexity
is the minimum needed for the current task. Before adding code, ask whether the
problem can be solved by making the existing code work better.

**Prefer:**
- Editing an existing function over adding a new abstraction
- Fixing the root cause over adding a workaround
- Deleting dead code over leaving it commented out

## Getting started

```bash
# Fork and clone
git clone https://github.com/<your-username>/symbiote-ai.git
cd symbiote-ai

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Copy env template and fill in keys for manual testing
cp .env.example .env
```

## Running tests

```bash
pytest tests/ -v
```

All tests must pass before submitting a PR. New behaviour must include new tests.

## Coding conventions

- **Python 3.11+** — use modern syntax (`str | None`, `match`, etc.)
- **Type hints** on all function signatures
- **No print statements** — use `get_logger(__name__)` from `src/logger.py`
- **No silent failures** — log errors explicitly; let callers handle recovery
- **Config lives in `src/config.py`** — never hardcode values that operators might need to change
- **DRY_RUN stays `true` by default** — never change this default in a PR

## Making changes

1. Create a feature branch: `git checkout -b feat/my-improvement`
2. Make your changes and add tests
3. Run `pytest tests/` — all 24+ tests must pass
4. Commit with a clear message explaining *why*, not just *what*
5. Open a pull request against `main` and fill in the PR template

## Commit message format

```
Short imperative summary (max 72 chars)

Optional body explaining the motivation and any non-obvious decisions.
Keep lines under 80 chars.
```

Good: `Add follow-up email logic after 7-day silence`
Bad: `updated negotiate.py`

## Areas we'd love help with

- **Follow-up sequences** — send a gentle bump if no reply after N days
- **Reply parsing** — detect positive/negative intent in incoming emails
- **Multi-profile scouting** — run scout against multiple profiles in one command
- **Postgres support** — swap `get_connection()` for a configurable backend
- **Richer verification** — headless browser fallback for JS-heavy partner sites

## Reporting security issues

Please do **not** open a public issue for security vulnerabilities. Email the
maintainers directly (see the GitHub Security tab for the private disclosure
channel).

## License

By contributing, you agree that your changes will be licensed under the
[MIT License](LICENSE).
