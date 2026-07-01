# ExperimentIQ

A multi-agent AI system for product experimentation. Four specialized LangGraph agents — each with its own typed state, narrow task, and stateless Claude Sonnet call — cover the full experiment lifecycle: discover opportunities from behavioral data, design statistically sound tests, monitor running experiments daily, and interpret results with a defensible verdict.

Built for growth teams at Series A/B startups who had the experiment platforms (GrowthBook, LaunchDarkly, Statsig) and the analytics (GA4, Amplitude, Mixpanel) but lacked the data science layer to connect those signals, run rigorous tests, and make defensible ship/don't-ship decisions from the results.

---

## The Architecture

This is the core of the system. Everything else — the UI, the integrations, the daily email — exists to wire data into and out of these four agents.

> **[▶ Open Interactive Architecture Diagram](architecture.html)** — animated data-flow diagram showing all four agents, their internal node pipelines, inputs, outputs, compute layer, and infrastructure. Open in any browser.

The system is a left-to-right pipeline: analytics data enters on the left, passes through one or more LangGraph agents in the center, and produces structured Pydantic outputs on the right. All agents share a compute layer (Claude Sonnet + NumPy/SciPy stats engine) below them.

```
┌─────────────────┐          ┌──────────────────────────────────────────────────┐          ┌──────────────────────┐
│   Data Inputs   │          │            LangGraph Agent Pipeline               │          │       Outputs        │
│                 │          │                                                    │          │                      │
│  GA4            │ ───────► │  ① Opportunity Agent  (5 nodes · RAG)            │ ───────► │  Ranked Opportunities│
│  Amplitude      │          │     ingest → rag → candidates → rank → report     │          │                      │
│  Mixpanel       │          │                                                    │          │                      │
│  CSV / Datasets │          │  ② Framing Agent      (4 nodes)                  │ ───────► │  ExperimentDesign    │
│                 │          │     parse → constraints → design → validate        │          │                      │
│                 │          │                                                    │          │                      │
│                 │          │  ③ Monitoring Agent   (3 nodes · automated daily) │ ───────► │  Daily Email         │
│                 │          │     fetch → stat_checks → synthesize              │          │  via SendGrid        │
│                 │          │                                                    │          │                      │
│  Assignment Log │ ───────► │  ④ Interpretation Agent (4 nodes)                │ ───────► │  Ship / Don't Ship   │
│  + Event Log    │          │     fetch → significance_tests → interpret → build│          │  / Run Longer        │
└─────────────────┘          │                                                    │          └──────────────────────┘
                             │          ↑ all agents call ↓                      │
                             │  ┌─────────────────────┐  ┌─────────────────────┐│
                             │  │  Claude Sonnet       │  │  Stats Engine       ││
                             │  │  stateless per node  │  │  NumPy · SciPy      ││
                             │  └─────────────────────┘  └─────────────────────┘│
                             └──────────────────────────────────────────────────┘
```

---

## The Four Agents

### Agent 1 — Opportunity Discovery

**File:** `backend/agents/opportunity_agent.py`

Five-node LangGraph pipeline. Takes a behavioral dataset and produces ranked, hypothesis-backed experiment opportunities with lift estimates grounded in the actual data.

```
ingest_and_analyze → retrieve_context → generate_candidates → score_and_rank → build_report
       ↓ (fetch_failed)                                                              ↑
       └─────────────────────────────────────────────────────────────────────────────┘
```

| Node | Claude's role | Output added to state |
|---|---|---|
| `ingest_and_analyze` | Analyze funnel drop-offs and segment gaps | `funnel_analysis`, `segment_analysis` |
| `retrieve_context` | — (vector store RAG query, no LLM) | `rag_context` (top 10 chunks) |
| `generate_candidates` | Generate 8–10 specific, data-grounded hypotheses | `opportunity_candidates` |
| `score_and_rank` | Score by impact × evidence × effort, rank top 5, output JSON | `scored_opportunities` |
| `build_report` | — (Pydantic assembly, no LLM) | `OpportunityReport` |

**State schema** (`OpportunityState` TypedDict):
```python
company_description: str
current_metrics: dict[str, float]
data_source: str                      # "demo" | "csv" | "ga4" | "amplitude"
csv_content: str | None
analytics_summary: AnalyticsSummary | None
vector_store: SimpleVectorStore | None
funnel_analysis: str
segment_analysis: str
rag_context: list[str]
opportunity_candidates: str
scored_opportunities: str
report: OpportunityReport | None
fetch_failed: bool
failure_reason: str
```

**Output model:**
```python
class ExperimentOpportunity(BaseModel):
    rank: int
    title: str
    hypothesis: str
    primary_metric: str
    estimated_lift_low_pct: float
    estimated_lift_high_pct: float
    risk_level: str           # "low" | "medium" | "high"
    effort_level: str         # "low" | "medium" | "high"
    evidence: str             # the specific data point that justifies this
    expected_impact_score: float   # 0.0–1.0
    segment_to_watch: str
```

**What makes this AI engineering:** Claude doesn't just "give ideas." Node 1 makes two separate Claude calls — one for funnel analysis, one for segment analysis — each scoped to a single analytical question. Node 2 uses a vector store (cosine similarity over pre-computed embeddings) to retrieve the most relevant data chunks before Claude sees them in Node 3. Node 4 scores with explicit criteria (gap size, evidence quality, effort ratio) and is retried once on JSON parse failure. The final node uses Pydantic to validate every opportunity field — malformed outputs are dropped, not silently passed through.

---

### Agent 2 — Experiment Framing

**File:** `backend/agents/framing_agent.py`

Four-node pipeline. Takes a raw hypothesis string and returns a structured `ExperimentDesign` with everything a DS would need to set up the experiment correctly.

```
parse_hypothesis → retrieve_constraints → design_experiment → validate_design
```

| Node | Claude's role | Output |
|---|---|---|
| `parse_hypothesis` | Extract intent, proposed metrics, and runtime hints from free text | `intent`, `proposed_metrics`, `runtime_estimate` |
| `retrieve_constraints` | — (context lookup, no LLM) | `constraints` |
| `design_experiment` | Produce full experiment design as structured JSON | `ExperimentDesign` (draft) |
| `validate_design` | Check for statistical validity — MDE feasibility, guardrail coverage | `ExperimentDesign` (validated) |

**Output model:**
```python
class ExperimentDesign(BaseModel):
    hypothesis: str
    primary_metric: str
    metric_rationale: str
    guardrail_metrics: list[str]
    unit_of_randomization: str
    estimated_runtime_days: int
    minimum_detectable_effect: float
    tradeoffs: list[str]
    clarifying_questions: list[str]
    confidence: float           # 0.0–1.0
```

This output is what gets sent to GrowthBook, LaunchDarkly, or Statsig to create the experiment.

---

### Agent 3 — Experiment Monitoring

**File:** `backend/agents/monitoring_agent.py`

Three-node pipeline. Runs daily against every active experiment on connected platforms. Stats are computed in Python first — Claude synthesizes, never calculates.

```
fetch_data → run_stat_checks → synthesize_health
    ↓ (fetch_failed)                  ↑
    └─────────────────────────────────┘
```

| Node | What runs | Claude's role |
|---|---|---|
| `fetch_data` | GrowthBook API + BigQuery for metric observations | — |
| `run_stat_checks` | Python: SRM, novelty, sequential test, CUPED | — |
| `synthesize_health` | — | Interprets stat check outputs, produces `summary` and `suggested_actions` |

**Stats computed before Claude sees anything:**

```python
# SRM Detection — chi-square goodness-of-fit
srm: SRMResult = stats.check_srm(variation_counts, expected_split=0.5)
# p < 0.01 → has_srm = True → health_status forced to "critical"

# Novelty Detection — early vs late window lift ratio
novelty: NoveltyResult = stats.check_novelty(time_series_data)
# early_lift / late_lift > 1.5 → novelty_detected = True

# Sequential Testing — O'Brien-Fleming alpha spending
seq: SequentialTestResult = stats.sequential_test(observations, alpha=0.05)
# boundary = z_alpha / sqrt(information_fraction)
# returns: can_stop, recommendation ("stop_ship" | "stop_abandon" | "continue")

# CUPED — OLS variance reduction using pre-experiment covariates
cuped: CupedResult = stats.apply_cuped(pre_observations, post_observations)
# theta = cov(pre, post) / var(pre)
# skipped if < 10 users have pre-experiment data
```

**Output model:**
```python
class MonitoringReport(BaseModel):
    experiment_id: str
    health_status: str              # "healthy" | "warning" | "critical"
    srm_check: SRMResult | None
    data_quality: DataQualityResult | None
    sequential_test: SequentialTestResult | None
    novelty_check: NoveltyResult | None
    summary: str
    suggested_actions: list[str]
    confidence: float
```

This is emailed daily via SendGrid. LaunchDarkly and Statsig experiments get status tracking only — full monitoring requires GrowthBook's metric access.

---

### Agent 4 — Post-Experiment Interpretation

**File:** `backend/agents/interpretation_agent.py`

Four-node pipeline. Takes raw assignment + event logs, runs the full statistical pipeline, then passes the computed results to Claude for interpretation. Claude never sees raw data — only pre-computed statistics.

```
fetch_results → run_significance_tests → interpret_with_claude → build_recommendation
      ↓ (data_quality_failed)                                            ↑
      └────────────────────────────────────────────────────────────────────┘
```

| Node | What runs | Claude's role |
|---|---|---|
| `fetch_results` | GrowthBook results + BigQuery events, data quality checks | — |
| `run_significance_tests` | z-test, Welch's t-test, guardrail z-tests, 95% CIs | — |
| `interpret_with_claude` | — | Synthesizes pre-computed stats into verdict, narrative, risks, follow-up cuts |
| `build_recommendation` | Pydantic assembly and validation | — |

**Stats pipeline (Python, before Claude):**

```python
# Conversion rate: two-proportion z-test with pooled SE
p_pool = (conv_ctrl + conv_trt) / (n_ctrl + n_trt)
SE = sqrt(p_pool * (1 - p_pool) * (1/n_ctrl + 1/n_trt))
z = (p_trt - p_ctrl) / SE
p_value = 2 * (1 - norm.cdf(abs(z)))

# Revenue per user: Welch's t-test (unequal variance)
t_stat, p_value = ttest_ind(revenue_ctrl, revenue_trt, equal_var=False)

# Guardrails: each guardrail event type gets its own z-test
# Any guardrail that degrades at p < 0.05 flags the recommendation

# 95% CI on relative lift via normal approximation
ci_low = lift - 1.96 * SE_lift
ci_high = lift + 1.96 * SE_lift
```

Claude receives a structured context containing only: z-scores, p-values, relative lifts, CIs, guardrail flags, SRM result, novelty flag, and the experiment hypothesis. It produces a verdict from evidence — not from raw data.

**Output model:**
```python
class Recommendation(BaseModel):
    experiment_id: str
    decision: str               # "ship" | "iterate" | "abandon"
    confidence: float           # 0.0–1.0
    primary_metric_summary: str
    guardrail_summary: str
    reasoning: str
    follow_up_cuts: list[str]
    risks: list[str]
    data_quality_passed: bool
    created_at: datetime
```

---

## What AI Engineering Looks Like Here

Most LLM apps are one prompt → one response. This is not that.

**Typed state threading.** Each agent uses a `TypedDict` as its state schema. LangGraph passes state between nodes as partial updates — every node declares exactly what it writes, and undeclared keys are silently dropped. State is never mutated in place.

**Stateless calls at every node.** Every Claude call is independent — no conversation history, no accumulated context. Each node gets exactly the context it needs, nothing it doesn't. This keeps calls auditable, predictable, and debuggable.

**Stats first, Claude second.** The monitoring and interpretation agents never ask Claude to compute statistics. NumPy and SciPy handle SRM detection, z-tests, Welch's t-tests, sequential testing, and CUPED. Claude only sees pre-computed numbers and decides what they mean. This isn't just about accuracy — it means the statistical outputs are reproducible and verifiable independent of the LLM.

**RAG inside the opportunity agent.** Node 2 (`retrieve_context`) queries a `SimpleVectorStore` built from the ingested analytics data — cosine similarity over TF-IDF embeddings. The most relevant chunks are injected into the Claude prompt for Node 3. This grounds candidate generation in specific data signals rather than general experimentation knowledge.

**Conditional edges for failure handling.** Each agent graphs a `fetch_failed` path that bypasses the middle nodes and routes directly to `build_report`/`build_recommendation` with a structured error output. The system never surfaces a raw exception to the API caller.

**Pydantic at every boundary.** Agent outputs are Pydantic models (`OpportunityReport`, `ExperimentDesign`, `MonitoringReport`, `Recommendation`). Malformed LLM outputs are caught at validation, logged, and handled — never passed downstream silently.

**Automated pipeline.** The monitoring agent runs daily via APScheduler without any user trigger. It iterates all connected users, fetches experiments, runs the stat checks, writes snapshots to SQLite, and sends a formatted HTML email via SendGrid. The APScheduler job and its health endpoint exist so you can verify the pipeline is alive.

---

## Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph, TypedDict, conditional edges) |
| AI model | Claude Sonnet (Anthropic) — stateless call per node |
| Stats engine | NumPy + SciPy — SRM, z-test, Welch's t, sequential, CUPED |
| RAG | SimpleVectorStore — cosine similarity, TF-IDF embeddings |
| Backend | FastAPI |
| Experiment platforms | GrowthBook (self-hosted), LaunchDarkly, Statsig |
| Analytics integrations | Google Analytics 4 (OAuth 2.0), Amplitude, Mixpanel |
| Daily scheduling | APScheduler (AsyncIOScheduler + CronTrigger at 6 AM EST) |
| Email | SendGrid |
| Snapshot storage | SQLite via aiosqlite |
| Frontend | Next.js 14 (App Router) |
| Auth | Clerk |
| Credential encryption | Fernet (cryptography) — encrypted to disk on named Docker volume |
| Local dev | Docker Compose |

---

## User-Facing Paths

Three entry points from the landing hub at `/select`. Each one feeds data into one or more agents above.

### Path 1 — Opportunity Discovery from Datasets

Upload any behavioral CSV (or pick from four pre-built ones: Google Merchandise Store, Olist E-Commerce, Instacart, Telco Churn). Feeds **Agent 1** (Opportunity Discovery).

One click from each opportunity to frame it and start the experiment in GrowthBook, LaunchDarkly, or Statsig — that click runs **Agent 2** (Framing).

### Path 2 — Live Analytics (GA4, Amplitude, Mixpanel)

Connect your analytics platform via OAuth 2.0 or API key. Live data feeds **Agent 1** directly, bypassing the CSV step. Platform setup interstitial lets you connect GrowthBook / LaunchDarkly / Statsig inline before seeing opportunities.

### Path 3 — Post-Experiment Interpretation

Upload raw assignment log (`user_id, variant, timestamp`) + event log (`user_id, event_name, timestamp, revenue`). Runs **Agent 4** (Interpretation) directly — no GrowthBook connection required.

### Daily Monitoring (Automated)

**Agent 3** (Monitoring) runs automatically at 6 AM EST for every user with a connected experiment platform. No user action required. Output arrives by email.

---

## Project Structure

```
experimentiq/
├── backend/
│   ├── agents/
│   │   ├── opportunity_agent.py        # Agent 1: 5-node LangGraph, OpportunityReport
│   │   ├── framing_agent.py            # Agent 2: 4-node LangGraph, ExperimentDesign
│   │   ├── monitoring_agent.py         # Agent 3: 3-node LangGraph, MonitoringReport
│   │   └── interpretation_agent.py    # Agent 4: 4-node LangGraph, Recommendation
│   ├── api/
│   │   ├── datasets.py                 # Dataset upload → Agent 1
│   │   ├── analytics.py                # GA4 OAuth + live data → Agent 1
│   │   ├── experiments.py             # Frame (Agent 2), list, get
│   │   ├── start_experiment.py        # Create in GrowthBook / LaunchDarkly / Statsig
│   │   ├── monitoring.py              # Agent 3 endpoint
│   │   ├── experiment_interpret.py     # Raw log upload → Agent 4
│   │   ├── interpretation.py          # Agent 4 endpoint (GrowthBook path)
│   │   ├── reports.py                 # Daily report history + manual trigger
│   │   └── health.py
│   ├── services/
│   │   ├── stats.py                   # SRM, novelty, sequential, CUPED, z-test, t-test
│   │   ├── experiment_stats.py         # Post-experiment full stats pipeline
│   │   ├── analytics_ingestion.py     # GA4 normalization → AnalyticsSummary
│   │   ├── vector_store.py            # SimpleVectorStore (cosine similarity, TF-IDF)
│   │   ├── growthbook.py              # GrowthBook REST API client
│   │   ├── launchdarkly.py            # LaunchDarkly REST API v2 client
│   │   ├── statsig.py                 # Statsig API client
│   │   ├── oauth_store.py             # Fernet-encrypted credential store
│   │   ├── experiment_tracker.py      # Daily job: fetch → monitor → snapshot → email
│   │   ├── scheduler.py               # APScheduler (CronTrigger 6 AM EST)
│   │   ├── notifier.py                # SendGrid daily report email
│   │   ├── db.py                      # SQLite: experiment_snapshots, daily_reports
│   │   └── bigquery.py                # BigQuery metric observations
│   ├── middleware/
│   │   ├── auth.py                    # Clerk JWT validation
│   │   ├── rate_limit.py              # SlowAPI (10 req/min per user on LLM endpoints)
│   │   └── logging.py                 # Structured JSON request logging
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── select/page.tsx            # Three-path hub
│   │   ├── datasets/page.tsx          # Dataset upload + opportunity display
│   │   ├── analytics/page.tsx         # GA4 + experiment platform setup interstitial
│   │   ├── interpret/page.tsx         # Raw log upload + Agent 4 results
│   │   ├── experiments/page.tsx       # Platform connections (GB / LD / Statsig)
│   │   ├── experiments/new/           # Framing wizard (Agent 2)
│   │   └── experiments/[id]/          # Detail, monitoring (Agent 3), interpretation (Agent 4)
│   ├── components/
│   │   └── ExperimentDetailModal.tsx  # Multi-platform launch UI
│   └── lib/
│       ├── api.ts                     # Typed FastAPI client
│       └── auth.ts                    # Clerk session token helper
├── docker-compose.yml
├── ubereats_assignment.csv            # Demo: social proof experiment → Ship
├── ubereats_events.csv
├── linkedin_assignment.csv            # Demo: AI connection requests → Don't Ship
└── linkedin_events.csv
```

---

## API Endpoints

| Method | Path | Agent |
|---|---|---|
| POST | `/api/v1/datasets/analyze` | Agent 1 (Opportunity) |
| GET | `/api/v1/auth/google/authorize` | — OAuth flow |
| POST | `/api/v1/auth/google/callback` | — public route |
| GET | `/api/v1/auth/google/status` | — |
| POST | `/api/v1/analytics/analyze` | Agent 1 (live GA4 data) |
| POST | `/api/v1/experiments/frame` | Agent 2 (Framing) |
| GET | `/api/v1/experiments` | GrowthBook list |
| GET | `/api/v1/experiments/{id}` | GrowthBook detail |
| GET | `/api/v1/experiments/{id}/monitor` | Agent 3 (Monitoring) |
| POST | `/api/v1/experiments/{id}/interpret` | Agent 4 (Interpretation, GrowthBook path) |
| POST | `/api/v1/experiments/interpret/` | Agent 4 (raw CSV path) |
| POST | `/api/v1/experiments/start` | Create in GB / LD / Statsig |
| GET | `/api/v1/experiments/platform-status` | Connected platform check |
| POST | `/api/v1/experiments/connect-launchdarkly` | — |
| POST | `/api/v1/experiments/connect-statsig` | — |
| GET | `/api/v1/reports/history` | Daily report history |
| GET | `/api/v1/reports/snapshots` | Experiment snapshots by date |
| POST | `/api/v1/reports/run-now` | Manual daily job trigger |
| GET | `/api/v1/reports/scheduler-status` | Next scheduled run |
| GET | `/health` | — |

LLM endpoints rate-limited to 10 req/min per user. All endpoints except `/health`, the OAuth callback, and `/api/v1/reports/run-now` (with `X-Admin-Secret` header) require a valid Clerk JWT.

---

## Demo CSV Files

**Social Proof Experiment** (`ubereats_assignment.csv` + `ubereats_events.csv`)

10,100 users. Treatment: +23.1% lift on `order_placed` (18.0% → 22.2%). All guardrails pass. Verdict: **Ship**.

Metadata to enter: hypothesis = "Adding social proof (order counts, ratings) to restaurant cards will increase users clicking through to place orders", target event = `order_placed`

**AI Feature Experiment** (`linkedin_assignment.csv` + `linkedin_events.csv`)

9,700 users. Treatment: +19% on the primary engagement event. But connection removal rate +162%, spam signal +214%. Verdict: **Don't Ship** — primary metric improved, guardrails failed.

Metadata to enter: hypothesis = "AI-generated connection request messages will increase connection acceptance rates by reducing friction in the request-writing step", target event = `connection_accepted`

These two cases are intentionally contrasting. The LinkedIn case is the more important demo — it shows the system making the correct call when the primary metric is misleading.

---

## Quick Start (Docker)

**1. Clone and configure**

```bash
git clone https://github.com/nishaanjoshi0/experimentiq.git
cd experimentiq
```

Root `.env` (MongoDB for GrowthBook):
```
MONGO_USERNAME=admin
MONGO_PASSWORD=yourpassword
```

`backend/.env`:
```
ENVIRONMENT=development
ANTHROPIC_API_KEY=your-anthropic-key
CLERK_JWKS_URL=https://your-clerk-domain/.well-known/jwks.json
CLERK_SECRET_KEY=your-clerk-secret-key

GROWTHBOOK_API_URL=http://growthbook:3100
GROWTHBOOK_API_KEY=your-growthbook-key

GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:3001/api/auth/callback/google

# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
OAUTH_ENCRYPTION_KEY=your-fernet-key
CREDENTIAL_STORE_PATH=/app/data/creds.json

SENDGRID_API_KEY=your-sendgrid-key
NOTIFY_FROM_EMAIL=reports@yourdomain.com
NOTIFY_FROM_NAME=ExperimentIQ
NOTIFY_TO_EMAIL=you@yourdomain.com
DAILY_JOB_HOUR_UTC=11
DAILY_JOB_MINUTE_UTC=0

ADMIN_SECRET=your-admin-secret
ALLOWED_ORIGINS=http://localhost:3001
```

`frontend/.env.local`:
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your-publishable-key
CLERK_SECRET_KEY=your-clerk-secret-key
FASTAPI_BASE_URL=http://backend:8000
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/select
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/select
```

**2. Start**

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3001 |
| Backend API | http://localhost:8000 |
| GrowthBook UI | http://localhost:3000 |
| GrowthBook API | http://localhost:3100 |

Open GrowthBook, create an admin account, generate an API key, add it to `backend/.env` as `GROWTHBOOK_API_KEY`, then `docker compose restart backend`.

---

## Local Setup

**Backend**
```bash
cd backend
pip install -r requirements.txt
# create backend/.env (use GROWTHBOOK_API_URL=http://localhost:3100)
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
# create frontend/.env.local (use FASTAPI_BASE_URL=http://localhost:8000)
npm run dev -- --port 3001
```

**GrowthBook** (Docker)
```bash
docker compose up -d
```

---

## Triggering the Daily Report Manually

```bash
curl -X POST http://localhost:8000/api/v1/reports/run-now \
  -H "X-Admin-Secret: your-admin-secret"

curl http://localhost:8000/api/v1/reports/scheduler-status \
  -H "Authorization: Bearer your-clerk-jwt"
```

---

## Statistical Methods

All implemented from scratch in `backend/services/stats.py` and `backend/services/experiment_stats.py`.

**Two-proportion z-test** — pooled SE: `p_pool = (conv_ctrl + conv_trt) / (n_ctrl + n_trt)`, `SE = sqrt(p_pool * (1 - p_pool) * (1/n_ctrl + 1/n_trt))`. Two-tailed p via `scipy.stats.norm.cdf`. 95% CI via normal approximation on relative lift.

**Welch's t-test** — `scipy.stats.ttest_ind(equal_var=False)` for revenue. Correct for real experiment data where variance is almost never equal.

**SRM detection** — `scipy.stats.chisquare` on observed vs expected split. Flags at p < 0.01.

**Novelty detection** — early vs late window lift ratio. Flags when early lift / full lift > 1.5 and both are positive.

**CUPED** — OLS regression on pre-experiment covariates. `theta = cov(pre, post) / var(pre)`. Skipped when fewer than 10 users have pre-experiment data.

**Sequential testing** — O'Brien-Fleming alpha spending. `boundary = z_alpha / sqrt(information_fraction)`. Returns `stop_ship`, `stop_abandon`, or `continue`.

---

## Security

- All secrets loaded from environment variables.
- Clerk JWT validated on every request via JWKS endpoint with 5-minute local cache.
- GA4 OAuth callback and admin report trigger are the only public non-health paths.
- Experiment platform credentials stored Fernet-encrypted on a Docker named volume (`credsdata`). Not plaintext, not in-memory.
- Next.js proxies all FastAPI calls server-side — credentials never reach the browser.
- Claude calls are stateless — no experiment data accumulates in conversation history.

---

## Key Design Decisions

**Stats first, Claude second.** The monitoring and interpretation agents compute all statistics in Python before passing results to Claude. Claude interprets evidence — it doesn't calculate. This makes statistical outputs reproducible, verifiable, and independent of the model.

**Four agents with narrow scope instead of one large prompt.** Each agent has a single job. The opportunity agent doesn't interpret results. The interpretation agent doesn't discover opportunities. Narrow tasks produce more reliable structured outputs than prompts that attempt everything at once.

**Typed state at every boundary.** `TypedDict` for LangGraph state, Pydantic for agent outputs. Malformed LLM responses are caught at the boundary and handled — never silently passed to the next node.

**Conditional edges for resilience.** Every agent graphs a `fetch_failed` path that routes to the terminal node with a structured error output. The API always returns a valid response shape.

**Always show all three experiment platforms.** Whether connected or not, GrowthBook / LaunchDarkly / Statsig are always visible in the launch UI. Connected = solid action button. Disconnected = grey outline link to the connections page.

**Experiment platform links point to the list view, not the individual experiment.** Deep-linking to a specific experiment by key isn't reliably supported across platform environments. Linking to the experiments list is stable and puts the user one click from their experiment regardless of environment.

**Fernet encryption for credential persistence.** In-memory stores wipe on restart. File-backed Fernet-encrypted JSON on a named Docker volume survives container recreations. The encryption key is stable via `OAUTH_ENCRYPTION_KEY` in `.env`.
