# Symbiote AI

**Autonomous partnership development for micro-SaaS companies.**

Symbiote AI scouts non-competing products that share your audience, drafts personalized
cold outreach proposing a 1-to-1 audience swap, and verifies the partnership placement
once a deal is live — all without human intervention between runs.

---

## How it works

Three independent stages coordinate through a shared SQLite database:

```
Scout ──► leads.db ──► Negotiate ──► leads.db ──► Verify ──► leads.db
  │                        │                          │
  │  Finds companies        │  Drafts + sends email    │  Confirms link/widget
  │  via Tavily search      │  via Resend              │  live on partner site
  └── status: scouted       └── status: pitched         └── status: live
```

Each stage can be triggered independently (cron-friendly) or run together via
the `pipeline` command.

---

## Prerequisites

- Python 3.11+
- API keys for:
  - [Anthropic](https://console.anthropic.com/) — LLM for extraction and email copy
  - [Tavily](https://tavily.com/) — deep web search for lead discovery
  - [Resend](https://resend.com/) — transactional email delivery (only needed for live sends)

---

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url> && cd symbiote-ai

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and fill in ANTHROPIC_API_KEY, TAVILY_API_KEY, (RESEND_API_KEY)

# 5. Initialise the database
python src/db.py
```

---

## Usage

All commands are available via the CLI entry point at `src/cli.py`.

### Run individual stages

```bash
# Stage 1 — discover leads
python src/cli.py scout --profile "indie makers and solo developers" --max-results 10

# Stage 2 — draft and preview emails (safe, no delivery)
python src/cli.py negotiate --dry-run

# Stage 2 — draft and deliver emails (requires RESEND_API_KEY + DRY_RUN=false in .env)
python src/cli.py negotiate --send

# Stage 3 — verify partner placements
python src/cli.py verify
```

### Run the full pipeline in one command

```bash
python src/cli.py pipeline --profile "solo SaaS founders" --dry-run
```

### Inspect the pipeline

```bash
python src/cli.py status
python src/cli.py status --status-filter pitched
```

### Cron example (daily cadence)

```cron
# Scout every day at 08:00, negotiate at 09:00, verify at 18:00
0 8  * * * cd /path/to/symbiote-ai && venv/bin/python src/cli.py scout
0 9  * * * cd /path/to/symbiote-ai && venv/bin/python src/cli.py negotiate --send
0 18 * * * cd /path/to/symbiote-ai && venv/bin/python src/cli.py verify
```

---

## Configuration reference

All values can be set as environment variables (or in `.env`):

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Powers extraction and email generation. |
| `TAVILY_API_KEY` | — | Required. Powers web search for lead discovery. |
| `RESEND_API_KEY` | — | Required for live sends. Safe to omit in dry-run mode. |
| `SENDER_EMAIL` | `partnerships@symbiote.ai` | From address (must match a verified Resend domain). |
| `SENDER_NAME` | `Head of Partnerships, Symbiote AI` | Display name in outbound emails. |
| `SYMBIOTE_DOMAIN` | `symbiote.ai` | Domain the Verify stage looks for on partner sites. |
| `DRY_RUN` | `true` | When `true`, emails are drafted and logged but never sent. |
| `SCOUT_MAX_RESULTS` | `5` | Tavily results per search query. |
| `EMAIL_RATE_LIMIT_SECONDS` | `2.0` | Pause between consecutive email sends. |
| `FAST_MODEL` | `claude-haiku-4-5` | Model used for structured data extraction (Scout). |
| `SMART_MODEL` | `claude-sonnet-4-5` | Model used for email copy generation (Negotiate). |

---

## Architecture decisions

### Why Claude instead of a cheaper model for email copy?

Partnership emails are read by real founders. The quality of the first sentence — the
personalised hook — determines whether anyone reads further. Claude Sonnet consistently
produces copy that sounds human and founder-to-founder, not AI-generated. Haiku handles
the cheaper structured-extraction task in the Scout stage.

### Why SQLite?

SQLite is zero-ops for a single-machine deployment (the right starting point for a
solo-founder tool). The schema is migration-safe via idempotent `ALTER TABLE` wrappers,
so upgrading to Postgres later requires only swapping `get_connection()`.

### Why DRY_RUN defaults to true?

Outbound cold email is irreversible. The default-safe posture ensures you always review
the drafted copy (`negotiate --dry-run`) before flipping the switch.

### Verify detection strategy

The Verify stage uses four signals in descending confidence:
1. `<a href>` pointing to our domain — direct backlink
2. `<img src>` referencing our domain — logo/banner placement
3. `<iframe src>` referencing our domain — widget embed
4. Plain-text brand mention — softest signal, still worth tracking

---

## Running tests

```bash
pytest tests/ -v
```

The test suite covers:
- Database initialisation and idempotent migrations (`test_db.py`)
- URL-level deduplication
- Email draft generation with mocked LLM calls (`test_negotiate.py`)
- Fallback email template when the LLM is unavailable
- HTML-based placement detection across all four signal types (`test_verify.py`)
- Network retry behaviour in the Verify fetch layer

---

## Project layout

```
symbiote-ai/
├── .env.example          environment variable template
├── requirements.txt      pinned dependencies
├── src/
│   ├── config.py         centralised configuration and validation
│   ├── logger.py         dual-output logging (console + daily log file)
│   ├── db.py             SQLite schema, migrations, and helper functions
│   ├── scout.py          Stage 1: lead discovery via Tavily + Claude
│   ├── negotiate.py      Stage 2: email drafting + delivery via Resend
│   ├── verify.py         Stage 3: HTTP-based placement verification
│   ├── pipeline.py       orchestrates all three stages in sequence
│   └── cli.py            Click-based command-line interface
├── tests/
│   ├── conftest.py       pytest path setup
│   ├── test_db.py        database layer tests
│   ├── test_negotiate.py email drafting tests
│   └── test_verify.py    placement detection tests
└── logs/                 auto-created; one log file per calendar day
```

---

## Email guardrails

The Negotiate module enforces strict rules in every generated email:

- **Never** mention money, compensation, equity, or revenue share
- **Never** use corporate buzzwords (synergy, leverage, unlock, game-changing)
- Body is capped at **3 sentences**: hook → shared audience → casual CTA
- Tone: casual, direct, founder-to-founder, 6th-grade reading level

These constraints live in the system prompt and are also enforced in the fallback template.
