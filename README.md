# GQH 2026 | Massive 8-K options research

One repository contains the official Massive starter notebook and this Systematic Trading study. The primary question is whether a covered call earns a larger **net increment over stock exposure** after a qualifying buyer agreement disclosure than on ordinary dates for the same tickers. A positive relative increment need not mean a profitable portfolio.

[HYPOTHESIS.md](HYPOTHESIS.md) is the unchanged pre-results hypothesis, committed as `63664eb` before the first IS run. [RULES.md](RULES.md) is the maintained rules/status reference; [RESEARCH_LOG.md](RESEARCH_LOG.md) records later diagnostics and implementation repairs. The two-page English note is `quant_note.pdf`; supporting references and aggregate evidence are in `reports/`. Main-track and Massive scores are separate. No stable edge, completed OOS study, or judges' sealed replication is claimed.

## Setup

The tested environment is WSL/Linux, Python **3.14.2**, with versions pinned in `requirements.txt`. From this repository root, with [uv](https://docs.astral.sh/uv/) installed:

```bash
uv venv --python 3.14.2 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python run_research.py --mode check
```

Configure `MASSIVE_API_KEY` locally using the ignored `.env` format in `.env.example`, or the process environment. The authenticating process loads the key into memory only; it must not print, return, log or commit the value. API access and sponsor entitlements are required for an uncached reproduction. No second data-provider key is needed by the current IS command.

The original `setup.sh` and `setup.ps1` are retained. For notebook inspection, open this folder in VS Code and choose its `.venv` kernel, or start `.venv/bin/python -m jupyter lab`. The root command below is the explicit reproduction entry point; importing the research modules does not execute the notebook.

## Reproduction

The root command supports three operational modes:

| Mode | Action |
|---|---|
| `check` | Run synthetic/offline tests; no market-data retrieval or actual study execution. |
| `complete-is` | Reproduce V1/V2 IS studies, apply the declared V3 causal portfolio repair, run each ledger's uniform diagnostics, export aggregates, and generate the draft note. |
| `report` | Regenerate reports/PDF from a completed original + corrected + causal bundle; no API requests or strategy rerun. |

Use a new ignored run directory for a new full reproduction:

```bash
.venv/bin/python run_research.py --mode complete-is --execute \
  --run-dir .massive_cache/research_runs/submission-is
```

Regenerate the report from that same completed run:

```bash
.venv/bin/python run_research.py --mode report \
  --run-dir .massive_cache/research_runs/submission-is
```

`--execute` enables the bounded IS stages only. `--offline` is not a full-command substitute: a cached study-only reproduction is available through `research/reproduce_is.py --offline`, while report mode is already offline. Missing inputs fail explicitly rather than triggering alternate event/contract selection. `--mode oos` fails closed until unseen-window eligibility and the complete readiness gate pass. Do not enable notebook flags to bypass that gate.

## Method and versions

The approved universe is the starter's static TOP100, with IS **2024-01-01 through 2025-12-31**. One economic category combines `acquisition_agreement` and `merger_agreement`: the buyer's first definitive agreement to acquire control of an operating business, with transaction/accession deduplication and the approved concurrent-news screen. Seller disclosures, historical references, nonbinding proposals, minority/debt transactions and later updates are not automatically equivalent signals.

The sole primary strategy is covered-call exposure implemented through the starter's parity-derived stock proxy. Contracts are fixed from `t_pre`: 90–180 calendar DTE nearest 120, with the sold call about 5% above pre-event spot. Entry uses the first full NYSE session close after the reviewed SEC clock; a premarket filing can enter at that same session close. The primary exit is **`t0 + 21` sessions**, capped at expiry, so the actual holding period need not be 21 sessions. An earlier press release may precede the filing and its pre-filing chain.

All required horizons, ordinary-date controls, uncertainty, stock comparison, category/expiry/OTM/timing sensitivities and doubled costs are retained. The primary cost model is a 5% haircut on each selected option leg's premium on each side; it is not an observed spread, commission or impact model. Full-path annual volatility, Sharpe and drawdown remain unavailable when daily NAV is incomplete. Complete metrics under the separate standing-NBBO assumption remain explicitly conditional.

| Version | Evidence and interpretation |
|---|---|
| V1 original | First IS output preserved. A clean-process cached reproduction matches the eleven audited table families at declared numerical tolerances. Legacy portfolio admission and valuation limitations remain. |
| V2 clock repair | A price-blind post-IS chronology audit restored Uber/Trendyol and Netflix/WBD because the prior exclusion reasons occurred after the correct entry close. The corrected study is separate; its regenerated ordinary-control realization also changes and is disclosed. |
| V3 lagged-state repair | Implemented, independently reviewed post-IS portfolio repair, evaluated once on saved V2 inputs with no HTTP. Orders use the entry-session-open decision clock and previous-close financial state; current closing prices/proceeds cannot determine admission or quantity. Corrected-V2 event tables are unchanged; the V3 ledger has 13 closed positions, two skips and one position open at window end. Its conditional standing-quote CAGR is about -0.64%, Sharpe -0.83, and maximum drawdown 1.72%. |

Quote diagnostics retain each version's original cashflows and decisions, with declared 60-second, 300-second and separate standing-state policies. They improve valuation evidence without repairing the legacy admission path or proving executable fills. Positions still open at the final IS session remain open; their last mark is not a sale, and no later scheduled-exit price is read. All-leg capacity diagnostics use the same twenty completed pre-entry sessions and never retrospectively reject or restore trades.

## Files and data boundaries

| Path | Purpose |
|---|---|
| `gator-quant-hacks-8k-options-challenge.ipynb` | Preserved first-IS strategy source with empty public outputs; the root CLI reproduces the later versioned evidence. |
| `HYPOTHESIS.md`, `RULES.md`, `RESEARCH_LOG.md` | Preregistration, maintained requirements/status, and versioned research provenance. |
| `run_research.py`, `research/`, `tests/` | One root CLI, controlled notebook-source extraction, diagnostics/report generators and offline tests. |
| `requirements.txt`, `.env.example`, `.gitignore` | Pinned dependencies, placeholder credential format and private-data exclusions. |
| `reports/`, `quant_note.pdf` | Generated allowlisted derived evidence and the two-page English draft note after successful report generation. |
| `.massive_cache/` | Ignored licensed responses, private snapshots, run manifests and detailed inputs/outputs. Never publish. |

Identical historical requests reuse shared private caches by complete request hash; they are immutable cached responses, not fresh observations. Original, corrected and causal run manifests and outputs stay separate. The report exporter publishes only allowlisted aggregates and derived portfolio curves, with file hashes and numeric/provenance checks. The executed notebook is privately archived; public notebook outputs are stripped and its strategy-code AST is unchanged. No raw option prices, volumes, filing text, private snapshots or authentication logs belong in Git.

## Remaining limits and submission

The automatic arbitrary-window classifier is **not ready**: complete filing exhibits and auditable acceptance/public-availability evidence are unavailable for the current automated pipeline. Manual IS labels and date arguments do not satisfy Massive's API-key-only unseen-window requirement. Contestant OOS **2026-01-01 through 2026-08-31** has not been evaluated; it remains blocked until source/classifier, clock, pricing, costs and reproduction are frozen and validated. Judges alone run the sealed window.

Synthetic parity, daily last trades and supplemental quote states retain dividend, financing, early-assignment, deliverable, synchronization and execution limitations. Static TOP100 selection, retrospective tags, a small dependent event sample and imperfect ordinary controls limit inference. Factor regressions and capacity screens do not establish causal alpha or scalable profit. Preserve failures, unavailable observations and post-IS changes.

Submit an English PDF and this public GitHub link on Devpost: [gqh-massive-8k-options](https://github.com/linnnnw0420/gqh-massive-8k-options). The core note remains at most two pages under the stricter local Massive instruction; references/appendix do not replace required core evidence. The generated note is a **draft/incomplete** artifact while OOS and unseen-window readiness remain unresolved. All team members must be listed. No Devpost submission is claimed.

Official sources: [Systematic Trading](https://www.gqhacks.com/tracks/systematic-trading), [Massive](https://www.gqhacks.com/tracks/systematic-trading/massive), the retained notebook Markdown, and [NYSE calendar](https://www.nyse.com/markets/hours-calendars). The maintained deadline conflict remains: verified pages showed October 4 at 11:00 AM ET, while the supplied brief showed 10:00 AM for Devpost and 11:00 AM for code. Prepare by 10:00 AM until an authoritative clarification resolves it.
