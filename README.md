<p align="center">
  <h1 align="center">🪸 Symbiote AI</h1>
  <p align="center"><strong>Autonomous partnership development for micro-SaaS companies.</strong></p>
  <p align="center">Scout. Enrich. Pitch. Follow up. Verify. Repeat — no sales team required.</p>
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

Symbiote AI is a headless, four-stage pipeline that runs on a cron job and grows
your audience without ad spend. It finds micro-SaaS companies that share your target
audience, enriches each lead by scraping their site for founder names and contact
emails, writes a hyper-personalised cold email proposing a 1-to-1 exposure swap,
follows up automatically on non-replies, and later confirms the placement appeared
on the partner's site.

**No financial transactions. No sales team. No manual outreach. CAN-SPAM compliant.**

```
$ symbiote pipeline --profile "indie makers and solo developers"

  ━━━━━━━━ Symbiote AI — Pipeline Run ━━━━━━━━
  [1/4] SCOUT
  ✓ Scout complete: 3 new lead(s).

  [2/4] ENRICH
  ✓ Enrich complete: 3 lead(s) enriched.

  [3/4] NEGOTIATE
  ✓ Negotiate complete: 2 pitch(es).

  [4/4] VERIFY
  ✓ Verify complete: 1/3 placement(s) confirmed.

  ╭─────────────────────────────╮
  │     Pipeline Summary        │
  │          live: 1            │
  │   negotiating: 0            │
  │       pitched: 2            │
  │      enriched: 0            │
  │       scouted: 0            │
  │      declined: 0            │
  ╰─────────────────────────────╯
```

---

## Why Symbiote?

- **Zero ad spend** — pure audience swaps; no financial transactions, ever
- **Lead scoring** — each company gets a 0–100 quality signal before any email is sent
- **Hyper-personalised copy** — Claude Sonnet hooks into the founder's name and tagline
- **CAN-SPAM compliant** — unsubscribe link in every email, opt-out stored in DB
- **Auto follow-up** — timed, LLM-written nudges for leads that went quiet
- **Reply detection** — inbound webhook classifies intent and updates pipeline status automatically
- **Safe by default** — `DRY_RUN=true` until you explicitly flip the switch
- **Cron-friendly** — each stage runs independently; no server required (except webhook)
- **Rich terminal UI** — coloured status tables and progress spinners built in
- **Fully auditable** — every email draft, score, and outcome lives in your local SQLite DB

---

## How it works

Four agents coordinate through a shared SQLite database:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Scout ──► Enrich ──► Negotiate ──► Verify                                  │
│    │          │            │            │                                    │
│    │  Tavily  │  Website   │  Claude    │  HTTP + BS4                        │
│    │  search  │  scraper   │  Sonnet    │  placement                         │
│    │  Claude  │  Lead      │  email     │  check                             │
│    │  Haiku   │  scoring   │  Resend    │                                    │
│    │          │            │            │                                    │
│  scouted  enriched      pitched        live                                  │
│                              │                                               │
│                         Follow-up ◄── Webhook (inbound replies)             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Stage | What it does | Tools |
|---|---|---|
| **Scout** | Searches Tavily for matching companies, extracts structured data | Tavily + Claude Haiku |
| **Enrich** | Visits homepage + about/contact pages, extracts emails, scores lead 0–100 | requests + BeautifulSoup |
| **Negotiate** | Drafts a personalised pitch with founder hook, delivers via Resend | Claude Sonnet + Resend |
| **Verify** | Fetches partner site, checks for backlinks, images, iframes, brand mentions | HTTP + BeautifulSoup |
| **Follow-up** | Sends timed nudges to pitched leads that haven't replied | Claude Sonnet + Resend |
| **Webhook** | Classifies inbound replies, handles CAN-SPAM unsubscribes | Flask + Claude Haiku |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/psreek-ai/symbiote-ai.git
cd symbiote-ai

# 2. Install (adds the `symbiote` CLI command)
make install
# or: pip install -e ".[dev]"

# 3. Configure
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and TAVILY_API_KEY at minimum

# 4. Initialise the database
python src/db.py

# 5. Discover and enrich leads (dry run — nothing is sent)
symbiote scout --profile "productivity tools for remote teams"
symbiote enrich
symbiote status

# 6. When ready to pitch
symbiote negotiate --send
```

---

## Commands

```bash
symbiote scout      --profile "..."    # discover new leads via Tavily + Claude
symbiote enrich                        # scrape sites, score leads
symbiote negotiate  --dry-run          # draft emails, log them, don't send
symbiote negotiate  --send             # draft AND deliver via Resend
symbiote followup   --dry-run          # draft follow-ups for quiet leads
symbiote followup   --send             # send follow-ups
symbiote verify                        # check partner sites for placement
symbiote status                        # Rich colour-coded table of the pipeline
symbiote export     --out leads.csv    # export all leads to CSV
symbiote webhook    --port 8080        # start inbound email + unsubscribe server
symbiote pipeline   --profile "..."    # run all four stages in one command
```

Every command accepts `--help` for full option documentation.

### Cron setup

```cron
# Scout + Enrich daily, pitch at 09:00, follow up at 10:00, verify at 18:00
0 7  * * * cd /path/to/symbiote-ai && venv/bin/symbiote scout
0 8  * * * cd /path/to/symbiote-ai && venv/bin/symbiote enrich
0 9  * * * cd /path/to/symbiote-ai && venv/bin/symbiote negotiate --send
0 10 * * * cd /path/to/symbiote-ai && venv/bin/symbiote followup  --send
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
| `MIN_LEAD_SCORE` | `40` | | Skip pitching leads scoring below this threshold |
| `FOLLOWUP_DELAY_DAYS` | `5` | | Days after pitch before first follow-up |
| `FOLLOWUP_MAX_COUNT` | `2` | | Maximum follow-up emails per lead |
| `WEBHOOK_PORT` | `8080` | | Port for the inbound email + unsubscribe server |
| `UNSUBSCRIBE_URL` | `http://localhost:8080/unsubscribe` | | Embedded in every outbound email |
| `FAST_MODEL` | `claude-haiku-4-5` | | Model for structured extraction |
| `SMART_MODEL` | `claude-sonnet-4-5` | | Model for email copy |

---

## Email guardrails

Every generated email enforces:

- **3 sentences maximum:** hook → shared audience → casual CTA
- **Tone:** casual, direct, founder-to-founder, 6th-grade reading level
- **Banned:** money, compensation, equity, revenue share, corporate buzzwords
- **CAN-SPAM footer:** every email includes a one-click unsubscribe link
- **Fallback template** fires automatically if the LLM is unreachable — no lead is silently skipped
- **Score gate:** leads below `MIN_LEAD_SCORE` are never pitched

---

## Project layout

```
symbiote-ai/
├── Makefile              make install / test / lint / db-reset
├── pyproject.toml        installable package + CLI entry point
├── requirements.txt      flat dependency list for pip install -r
├── LICENSE               MIT
├── CONTRIBUTING.md
├── src/
│   ├── config.py         all env-var backed configuration
│   ├── logger.py         console + daily file logging
│   ├── db.py             SQLite schema, migrations, helpers
│   ├── scout.py          Stage 1: Tavily search + Claude extraction
│   ├── enricher.py       Stage 2: website scraper, email discovery, lead scoring
│   ├── negotiate.py      Stage 3: Claude copy + Resend delivery
│   ├── verify.py         Stage 4: HTTP placement verification
│   ├── followup.py       Follow-up sequences for pitched leads
│   ├── webhook.py        Inbound email intent classification + unsubscribe endpoint
│   ├── pipeline.py       orchestrator: Scout → Enrich → Negotiate → Verify
│   └── cli.py            Click-based CLI entry point (Rich terminal UI)
├── tests/
│   ├── conftest.py
│   ├── test_db.py
│   ├── test_negotiate.py
│   ├── test_verify.py
│   ├── test_enricher.py
│   ├── test_followup.py
│   └── test_scout.py
└── logs/                 auto-created; one log file per calendar day
```

---

## Running tests

```bash
make test
# or: pytest tests/ -v
```

Tests cover database migrations, deduplication, email drafting (LLM mocked),
enricher parsing, follow-up draft logic, all four verification signal types,
and HTTP retry behaviour.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Areas where help is most welcome:

- **Postgres support** — swap the SQLite backend for production deployments
- **Headless browser verification** — Playwright fallback for JS-rendered partner sites
- **Dashboard** — a simple web UI to review and approve drafted emails before send
- **CRM integrations** — push pipeline status to HubSpot, Notion, Airtable

---

## License

[MIT](LICENSE) — use it, fork it, build your own BD machine.
