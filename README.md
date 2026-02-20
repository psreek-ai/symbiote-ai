<p align="center">
  <h1 align="center">🪸 Symbiote AI</h1>
  <p align="center"><strong>Autonomous partnership development for micro-SaaS companies.</strong></p>
  <p align="center">Scout. Pitch. Verify. Repeat — no sales team required.</p>
</p>

<p align="center">
  <a href="https://github.com/psreek-ai/symbiote-ai/actions/workflows/ci.yml">
    <img src="https://github.com/psreek-ai/symbiote-ai/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  </a>
  <a href="https://github.com/psreek-ai/symbiote-ai/issues">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome">
  </a>
</p>

---

Symbiote AI is a headless, three-stage pipeline that runs on a cron job and grows
your audience without ad spend. It finds micro-SaaS companies that share your target
audience, writes a personalized cold email proposing a 1-to-1 exposure swap
(newsletter cross-promotion or widget placement), sends it, and later confirms the
placement appeared on the partner's site.

**No financial transactions. No sales team. No manual outreach.**

```
$ symbiote pipeline --profile "indie makers and solo developers"

09:01:02 [INFO] [1/3] SCOUT
09:01:04 [INFO]   + New lead: Pika Labs <https://pika.app>
09:01:05 [INFO]   + New lead: Potion <https://potion.so>
09:01:06 [INFO]   + New lead: Typefully <https://typefully.com>
09:01:06 [INFO] Scout complete: 3 new lead(s).

09:01:06 [INFO] [2/3] NEGOTIATE
09:01:06 [INFO] DRY RUN mode — emails will be drafted and logged but NOT delivered.
09:01:08 [INFO] Drafting email for 'Typefully' → team@typefully.com
09:01:08 [INFO]   Subject: Quick audience swap idea — Typefully?
09:01:09 [INFO]   Marked 'Typefully' as 'pitched'.

09:01:09 [INFO] [3/3] VERIFY
09:01:11 [INFO]   VERIFIED: Backlink found: <a href='https://symbiote.ai/partner'>

09:01:11 [INFO] ─────────── PIPELINE SUMMARY ───────────
09:01:11 [INFO]          live: 1
09:01:11 [INFO]       pitched: 2
09:01:11 [INFO]       scouted: 0
```

---

## Why Symbiote?

- **Zero ad spend** — pure audience swaps; no financial transactions, ever
- **Founder-quality copy** — Claude Sonnet writes emails that read human, not AI-generated
- **Safe by default** — `DRY_RUN=true` until you explicitly flip the switch
- **Cron-friendly** — each of the three stages runs independently; no server required
- **Fully auditable** — every drafted email and its outcome lives in your local SQLite DB
- **URL deduplication** — companies already in the pipeline are never re-scouted

---

## How it works

Three agents coordinate through a shared SQLite database:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Scout ──► leads.db ──► Negotiate ──► leads.db ──► Verify     │
│     │                        │                        │         │
│     │  Tavily web search      │  Claude Sonnet email   │  HTTP   │
│     │  Claude Haiku extract   │  Resend delivery       │  check  │
│     │                        │                        │         │
│  status: scouted          status: pitched          status: live │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Stage | What it does | Models used |
|---|---|---|
| **Scout** | Searches Tavily for matching companies, extracts structured data | Claude Haiku (fast extraction) |
| **Negotiate** | Drafts a 3-sentence personalized pitch, delivers via Resend | Claude Sonnet (quality copy) |
| **Verify** | Fetches the partner's site, checks for backlinks, images, iframes, or brand mentions | HTTP + BeautifulSoup |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/psreek-ai/symbiote-ai.git
cd symbiote-ai

# 2. Install (adds the `symbiote` CLI command)
pip install -e ".[dev]"

# 3. Configure
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and TAVILY_API_KEY at minimum

# 4. Initialise the database
python src/db.py

# 5. Discover your first leads (dry run — nothing is sent)
symbiote scout --profile "productivity tools for remote teams"
symbiote negotiate --dry-run
symbiote status
```

---

## Commands

```bash
symbiote scout      --profile "..."   # discover new leads via Tavily + Claude
symbiote negotiate  --dry-run         # draft emails, log them, don't send
symbiote negotiate  --send            # draft AND deliver via Resend
symbiote verify                       # check partner sites for placement
symbiote status                       # table view of the full pipeline
symbiote pipeline   --profile "..."   # run all three stages in one command
```

Every command accepts `--help` for full option documentation.

### Cron setup

```cron
# Scout daily at 08:00, pitch at 09:00, verify at 18:00
0 8  * * * cd /path/to/symbiote-ai && venv/bin/symbiote scout
0 9  * * * cd /path/to/symbiote-ai && venv/bin/symbiote negotiate --send
0 18 * * * cd /path/to/symbiote-ai && venv/bin/symbiote verify
```

---

## Configuration

Copy `.env.example` to `.env` and set the values below:

| Variable | Default | Required | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | — | Yes | Powers extraction (Haiku) and email copy (Sonnet) |
| `TAVILY_API_KEY` | — | Yes | Deep web search for lead discovery |
| `RESEND_API_KEY` | — | For live sends | Transactional email delivery |
| `SENDER_EMAIL` | `partnerships@symbiote.ai` | | From address (must match verified Resend domain) |
| `SENDER_NAME` | `Head of Partnerships, Symbiote AI` | | Display name on outbound emails |
| `SYMBIOTE_DOMAIN` | `symbiote.ai` | | Domain the Verify stage looks for on partner sites |
| `DRY_RUN` | `true` | | Set `false` to actually deliver emails |
| `SCOUT_MAX_RESULTS` | `5` | | Tavily results per search query |
| `EMAIL_RATE_LIMIT_SECONDS` | `2.0` | | Pause between sends |
| `FAST_MODEL` | `claude-haiku-4-5` | | Model for structured extraction |
| `SMART_MODEL` | `claude-sonnet-4-5` | | Model for email copy |

---

## Email guardrails

Every generated email enforces:

- **3 sentences maximum:** hook → shared audience → casual CTA
- **Tone:** casual, direct, founder-to-founder, 6th-grade reading level
- **Banned:** money, compensation, equity, revenue share, corporate buzzwords
- **Fallback template** fires automatically if the LLM is unreachable — no lead is silently skipped

---

## Project layout

```
symbiote-ai/
├── pyproject.toml        installable package + CLI entry point
├── requirements.txt      flat dependency list for pip install -r
├── LICENSE               MIT
├── CONTRIBUTING.md
├── src/
│   ├── config.py         all env-var backed configuration
│   ├── logger.py         console + daily file logging
│   ├── db.py             SQLite schema, migrations, helpers
│   ├── scout.py          Stage 1: Tavily search + Claude extraction
│   ├── negotiate.py      Stage 2: Claude copy + Resend delivery
│   ├── verify.py         Stage 3: HTTP placement verification
│   ├── pipeline.py       orchestrator: Scout → Negotiate → Verify
│   └── cli.py            Click-based CLI entry point
├── tests/
│   ├── conftest.py
│   ├── test_db.py
│   ├── test_negotiate.py
│   └── test_verify.py
└── logs/                 auto-created; one log file per calendar day
```

---

## Running tests

```bash
pytest tests/ -v
```

24 tests covering database migrations, deduplication, email drafting (LLM mocked),
all four verification signal types, and HTTP retry behaviour.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Areas where help is most welcome:

- **Follow-up sequences** — bump leads that haven't replied in N days
- **Reply parsing** — detect positive/negative intent in incoming emails
- **Postgres support** — swap the SQLite backend for production deployments
- **Headless browser verification** — Playwright fallback for JS-rendered partner sites

---

## License

[MIT](LICENSE) — use it, fork it, build your own BD machine.
