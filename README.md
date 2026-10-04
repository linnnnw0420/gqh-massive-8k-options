# GQH 2026 — M&A-tagged filings and covered calls

One submission for the Systematic Trading main track and Massive subtrack.
**Current status:** IS and the single contestant OOS both completed with identical computational source; 23 offline tests passed. Primary event-minus-ordinary incremental estimate: IS +0.87 percentage points (exploratory 95% CI [-0.37, 2.17]); OOS +3.38 pp ([1.18, 5.85]). OOS event covered calls themselves average -3.38%, so a positive increment contrast does not establish profitability or option mispricing. Capital NAV gaps are 130/502 IS and 6/166 OOS sessions, including unavailable terminal marks; full-period capital return/risk metrics remain unavailable. No parameters were changed after OOS.

Open **submission.ipynb**. The final English PDF is submitted separately on Devpost. Paper source and saved analysis exports are kept outside this code repository; they are not runtime inputs.

## Setup and reproduce

```bash
uv venv --python 3.14.2 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python run_research.py --mode check
```

Set `MASSIVE_API_KEY` in the environment or ignored `.env` using `.env.example`.
The authenticating process loads it in memory; no key is printed or cached.
The submission needs Massive disclosures, historical option contracts and daily option bars, not SEC downloads, a second provider or private approval files.

Run the accepted version on IS:

```bash
.venv/bin/python run_research.py --mode submission --execute   --accept-operational-revision --start 2024-01-01 --end 2025-12-31
```

The owner already executed the following one-shot contestant OOS command. It is recorded for provenance; the journal blocks a second entrant evaluation:

```bash
.venv/bin/python run_research.py --mode submission --execute   --accept-operational-revision --approve-oos-once   --start 2026-01-01 --end 2026-08-31
```

The notebook exposes the same commands. Run switches default to False. The runner preserves immutable local results under `.massive_cache/submission_v4/`, requires the OOS source to match completed IS, and records the OOS outcome attempt before requesting option data. Existing attempts are never overwritten. Importing modules or Run All with unchanged switches does not execute either study. The global OOS journal is COMPLETE and must be preserved; do not rerun or retune.

For judges' supplied unseen dates, from a clean kernel:

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / 'research'))
from submission_variant import run_submission_study
study = run_submission_study(start_date, end_date, api_key, judges_window=True)
study.tables['theta_board']
```

Judges select that mode; entrants do not use it to bypass their one-shot OOS. This function uses the same event, pricing and risk definitions and needs only a key and dates. It does not rely on local IS identities or SEC files. Actual sealed performance is not claimed.

## Exact strategy

Version **LITERAL_TAG_UNION_POST_IS_V4**, explicitly adopted after the original IS:

- Literal Massive `acquisition_agreement OR merger_agreement` labels, official static TOP100; deduplicate accession and union tags. Include an accession only with one unambiguous TOP100 ticker. This does not assert buyer role, control, first announcement or independent transaction. Repeated deals, seller/minority/update filings can remain.
- Contract selection: regular session strictly before filing date. Entry: next regular NYSE session close. A labeled end-of-filing-day scheduling surrogate is not an actual SEC acceptance timestamp. No filing-day entry is presented as executable.
- One covered-call proxy: parity-derived stock plus a short call selected 5% OTM before the filing. Primary 90–180 DTE bucket, nearest 120 DTE; primary exit 21 sessions after entry, capped by expiry. Keep all eight official session horizons plus expiry.
- Cost: 5% of each option leg's premium on each side, including both parity legs; also report double costs. Flat parity carry 4%; idle cash and Sharpe risk-free convention 0. Daily last-trade marks are proxies, not executable NBBO quotes.
- Test event covered-call increment over the stock proxy against 120 ordinary date draws with seed 7 and a 30-calendar-day tagged-filing exclusion. Report every neighboring expiry/OTM/timing/category cell; do not select the best result.
- Capital ledger: $1 million, one contract per admitted event, at most one concurrent position per ticker, no leverage; name 10%, industry 25%, gross 100%, pause at 10% drawdown and resume below 5%. Orders use the prior completed session's state. The inherited 14-name industry map remains fixed: unmapped names are included in the event study but skipped in the capital ledger. These are different estimands.
- More-than-three-session stale or missing marks stay unavailable. No zero fill, interpolation, missing-return bridge or favorable event removal. Full-path Sharpe/volatility/drawdown/turnover stay unavailable when the NAV path is incomplete.

The conjecture is an event-specific option premium, not a prediction that every acquisition raises its buyer's stock. The current vendor-defined pool is broader than the original first-buyer economic screen; interpretation must reflect that change. See [RULES.md](RULES.md). Original pre-results hypothesis: commit `63664eb`; accepted V4 IS package: `b2dcec4`; completed one-shot OOS report: `d64caa3`. Earlier hypotheses, unsuccessful approaches and V1–V4 outcomes remain in Git history. V4 is a disclosed post-IS revision, not the original preregistration; no OOS retuning occurred. Each window retains all 972 correlated sensitivity cells. AI assisted research, implementation and drafting; the entrant remains responsible.

## What is here

| File | Purpose |
|---|---|
| `submission.ipynb` | Short notebook entry and result display; empty public outputs |
| `run_research.py` | Offline checks, bounded IS and one-shot contestant OOS |
| `strategy_defs.py` | Pure calculation definitions extracted unchanged from the starter |
| `research/` | Active clock, transport, study and causal capital calculation helpers |
| `tests/` | Offline synthetic checks of timing, boundaries, missingness and execution |
| `HYPOTHESIS.md` | Original pre-results hypothesis, unchanged |
| `RULES.md` | Maintained official rules; version provenance is recorded above and in Git |

Paper source, saved analysis tables and working drafts are archived outside this repository. Older inactive workflows remain in the ignored local archive and Git history. The hidden environment, private data cache and completed OOS journal remain local and must not be uploaded. The public project contains code, setup and reproduction instructions; the final PDF is a separate submission.

## Submit

On Devpost, submit the English PDF and a **public GitHub repository link** for both tracks; list every team member. The core note uses the stricter two-page notebook requirement, 11pt and standard margins. Local completion is not publication: public upload still needs the owner's approval.

Never commit keys, `.env`, `.massive_cache`, licensed raw prices/volumes or private snapshots. Public notebook outputs stay empty. Retain null/negative findings, unavailable results and version changes. Short samples, issuer overlap, the static universe, retrospectively supplied labels, mark/assignment/dividend/financing assumptions and unmeasured fills limit inference.

Deadline references conflict: prepare for October 4, **10:00 AM Eastern**, the earlier supplied Devpost deadline. Official sources and scoring are maintained in RULES.md; no score or profitable edge is guaranteed.
