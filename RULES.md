# GQH / Massive Rules and Project Status

**Canonical project reference. Last official-page verification: 2026-10-03; CH01--CH08 chapter audit and expanded guidance verified below.**

Read this file first whenever discussing competition rules, scoring, research progress or the next step. Do not repeat website searches for rules already captured here. Recheck an official source only if the user requests a refresh, an organizer supplies an update, a material conflict needs resolving, or this reference does not contain the needed rule. Record any verified change here. All repository code, comments and documentation are in English; conversation may be in Chinese.

This file separates official requirements, our frozen design, current implementation and proposed work. It does not grant execution permission or change the hypothesis. Later direct user instructions take precedence over local workflow notes. Older chat planning files contain historical execution states and are not the current status reference.

## 1. Sources and precedence

- Main track: https://www.gqhacks.com/tracks/systematic-trading
- Massive subtrack: https://www.gqhacks.com/tracks/systematic-trading/massive
- Official starter instructions retained in `gator-quant-hacks-8k-options-challenge.ipynb`, especially **What you submit**.
- User-supplied Participant Brief CH 01 excerpt and organizer announcements. The full independent brief has not been obtained; do not claim every chapter was independently checked.
- Pre-results project design: [HYPOTHESIS.md](HYPOTHESIS.md).

For main-track conflicts, the formal brief or organizer announcement governs over the explanatory webpage. For Massive-specific conflicts, the notebook or organizer announcement governs over its explanatory webpage. Record unresolved conflicts rather than silently choosing a convenient version.

**Page limit:** the two webpages allow a five-page PDF; the local official notebook requires a two-page write-up. Keep the core submission at two pages until an authoritative clarification permits otherwise. Main-track references/optional appendix exclusions do not automatically waive the notebook's stricter limit. Main-track formatting is at least 11pt with standard margins; judges need not read optional appendices.

**Deadline conflict:** the pages last verified on 2026-10-03 show Sunday October 4, 11:00 AM Eastern for Devpost and the final code push. The earlier user-supplied brief excerpt/screenshots show 10:00 AM for Devpost and 11:00 AM for code. This conflict is unresolved. Prepare to submit by 10:00 AM Eastern; do not repeatedly browse the countdown or assume a formal brief has changed.

## 2. Main-track requirements

Systematic Trading is the main track; Massive is a bonus inside the same submission. Scores are separate, not additive. GQH sends its ten strongest Massive entries to Massive for bonus judging. There is no P&L leaderboard; well-supported modest or null results can be valuable.

1. Write and commit the economic hypothesis before the first backtest. Explain the counterparty, proposed edge, persistence and falsification conditions.
2. Use cited, clean market data. Define the universe, handle corporate actions and missing/stale observations, and disclose selection and survivorship limitations.
3. Build a systematic signal, position sizing, realistic costs and risk controls. Use only information available before the decision/fill. A signal requiring a closing price cannot receive an assumed fill at that same close.
4. Report commissions/spread/slippage assumptions and justify cost units; show doubled costs. Net primary performance must not be replaced by favorable gross results.
5. Separate IS and OOS. Develop before viewing OOS, then evaluate OOS once after the design is fixed; do not return to tuning on it.
6. Report net annualized return, volatility, Sharpe, maximum drawdown, turnover and an equity curve, separately for IS and OOS. Our reporting convention uses calendar-time portfolio returns with declared capital, concurrent positions and idle cash; do not annualize overlapping event returns as independent daily observations.
7. Include risk limits, single-position loss analysis, gross/net exposure, downside/tail and de-risking plans, factor/correlation/regime evidence, and liquidity/capital/capacity analysis. CH07 explicitly recommends factor regression and a dollar capacity estimate; include these in the work queue rather than treating them as unrelated optional research. Assumptions are not measured execution evidence.
8. Disclose attempted ideas, failures and the number of variants tested. Do not report only the best parameter or significant comparison.
9. Cite data, papers and original code; identify what extends published/open-source work. AI tools are allowed, but the team remains responsible and must be able to explain the strategy and code; keep the AI-use disclosure for the final note.
10. Submit a PDF quant note and a public GitHub link on Devpost. Both are required. The user requires the final submission in English. Include README setup/reproduction instructions, a dependency file, all relevant code and data-download instructions. The code must reproduce the note's headline numbers. List all team members on Devpost.
11. Never publish API keys, `.env`, `.massive_cache` or licensed raw data. Review saved notebook outputs too; individual option prices/volumes are not automatically safe to publish merely because they appear in a notebook. Preserve the private first-run record and prepare a license-safe public version when packaging.

### Main-track scoring: 50 points

| Criterion | Maximum | Evidence expected |
|---|---:|---|
| Economic Foundation | 10 | Economic mechanism, counterparty, persistence, support and refutation. |
| Innovation | 10 | A specific contribution beyond familiar strategies and existing research. |
| Risk Management Plan | 10 | Name/industry/gross/net limits, downside/tail exposure and prior de-risking rules. |
| Liquidity & Capital | 10 | Sizing, capital use, spread/slippage/impact and defensible capacity. |
| Performance & Analytical Evidence | 10 | Fair comparisons, uncertainty, net costs, OOS, robust interpretation and reproducibility. |

Criterion 5 is capped at four if judges cannot run/reproduce the required results, or find lookahead/OOS tuning. Missing OOS today does not mean that cap has already been applied. Ties prioritize criterion 5, then Economic Foundation. Website score simulators and our internal estimates are not organizer grades.

The main track's general holdout rule is the latest 20% of history or two years, whichever is shorter. **The Massive notebook's OOS and judges' sealed windows replace this rule for this entry.** This exception was directly reverified in the Massive website's CH01 subtrack paragraph and footer on 2026-10-03; it is not inferred from our code configuration. Neither the verified pages nor the supplied CH 01 excerpt impose a mandatory 5–15-year backtest; teaching examples/sliders are not minimum-history requirements.

### Nine pitfalls to audit

| Official pitfall | Project check |
|---|---|
| P-hacking | Preserve the pre-results primary, every attempted variant and null/negative result. |
| Overfitting | Explain the small independent sample and avoid new profit-selected thresholds. |
| Lookahead bias | Check public clocks, selection timestamps, fills and retrospective labels separately. |
| Survivorship bias | Disclose the mandated static TOP100 and avoid claiming historical membership. |
| Ignoring costs | Report net results and doubled costs; distinguish premium haircuts from spreads. |
| Leaking the test set | Keep OOS untouched until freeze/readiness/approval; never inspect sealed data. |
| Misleading Sharpe | Require a complete NAV path; report skew and worst month alongside drawdown/Sharpe, and disclose overlap, small samples and short-call tail risk. |
| Regime dependence | Show yearly/concentration evidence and state what the short history cannot establish. |
| Unrealistic capacity | Assess all legs, participation, liquidity and capital; do not equate volume with fillability. |

## 3. Additional Massive requirements

- Use one or more actual disclosure categories and one primary strategy from the library: long call, covered call, protective put, collar or cash-secured put. Combining tags needs a consistent economic definition and transaction/accession deduplication.
- Test the official static TOP100. Whole-market disclosure retrieval is a discovery/coverage input, not automatic permission to expand the trading universe. Static TOP100 is not historical point-in-time membership.
- Official IS: **2024-01-01 through 2025-12-31**.
- Contestant OOS: **2026-01-01 through 2026-08-31**. The team eventually evaluates this once after freeze and readiness; it is not a judges-only period.
- **Sealed window is judges-only.** Its dates are chosen by judges. Placeholder notebook dates are not permission to inspect or test it.
- Report every fixed horizon: **1, 2, 3, 5, 10, 21, 42, 63 sessions, plus expiry**. Retain unavailable and expiry-capped cases with reasons rather than changing the horizons or manufacturing zero returns.
- Compare with ordinary dates for the same names; include uncertainty and the implied-versus-realized diagnostic. That diagnostic alone does not prove a particular option was mispriced or that a post-news entry can capture a pre-news repricing.
- Show neighboring expiry bucket, OTM, entry timing, horizon and category definitions. A sensitivity grid does not authorize selecting a new winner after observing IS.
- Respect public-information/filing lag. `pre` is a diagnostic, not an implementable event entry. News may precede the 8-K; do not describe the pre-filing chain as necessarily unaware of news.
- Retain the Massive disclosures/options study and explain synthetic-stock, last-trade, dividends/financing/assignment and execution limitations. Cite and approve any supplemental data rather than silently replacing the prescribed study.
- The final pipeline must accept start/end dates and run from a clean kernel with an API key on an unseen judges' window. A date signature plus a whitelist limited to IS does not meet this requirement.
- The notebook's all-five-strategy worked example is instructional, not a requirement to rank five strategies and override the pre-results main strategy.

### Massive scoring: 100 points

| Criterion | Maximum | Evidence expected |
|---|---:|---|
| Hypothesis and novelty | 30 | An economically motivated category-to-strategy link. |
| Analytical rigor | 30 | All horizons, controls, uncertainty, OOS and sensitivity. |
| Sealed-window replication | 20 | Replication, or correctly predicted fragility, on judges' unseen dates. |
| Trade realism | 10 | Public timing, defensible costs/liquidity and capacity. |
| Communication | 10 | A clear actionable note and runnable notebook. |

Baseline is one category/strategy/bucket plus interpretation; combined categories, timing, decay, placebo and realistic trade details are stretch evidence. Stretch work does not substitute for the required OOS and unseen-window pipeline.

## 4. Our frozen choices — not organizer-mandated parameters

- Primary event: first TOP100 buyer definitive agreement to acquire control of an operating business, from `acquisition_agreement` OR `merger_agreement`. Trade the buyer. The original H6 completion thesis is an abandoned/exploratory research branch, not the current primary strategy.
- Primary strategy: covered-call proxy with parity-derived stock exposure. Primary theta is the event-minus-ordinary difference in net covered-call increment over synthetic stock. Positive theta need not imply positive absolute profit.
- Select contracts on `t_pre`; 90–180 DTE nearest 120; sold call approximately 5% above **pre-event** spot. Keep the same contracts after news.
- Enter at the first full NYSE session close after the reviewed SEC acceptance clock. Primary exit is `t0 + 21` sessions, capped at expiry; actual holding length can differ from 21 sessions.
- Initial NAV $1,000,000; one contract per admitted signal, one concurrent position per ticker, no leverage, zero cash return. Stock-gross limits: name 10%, manual industry 25%, total 100%. Pause entries at 10% drawdown; resume strictly below 5%.
- Costs: 5% of each selected option leg's premium on each opening/closing side; double-cost stress. These are premium haircuts, not measured stock-basis-point fees or NBBO execution.
- Ordinary dates: up to 120 seed-7 draws with ticker/tag/acceptance-clock templates, away from agreement tags by 30 calendar days. They are neither one-to-one matches nor proven news-free days.
- Three expiry buckets, 3/5/10% OTM, declared timing scenarios and all horizons. The 972 correlated reporting cells are not 972 independent strategy tests.
- Last trades older than three sessions are unavailable. Do not extend this cutoff, interpolate, delete losing events or replace quotes to obtain prettier results.
- Sharpe: calendar daily returns, 252 sessions/year, rf=0. Basis points multiply a return fraction by 10,000; Sharpe is unitless. Frozen turnover is two-sided full-period gross/complete-calendar mean NAV; add a clearly named annualized reporting ratio for the main-track convention, retaining the full-period ratio.
- Endpoint CAGR can be known with interior NAV gaps. Full-path Sharpe/volatility/MDD/frozen turnover need complete inputs. Observed drawdown is only a lower bound; initial-capital turnover is a separate diagnostic. Daily-close MDD does not measure intraday drawdown.

## 5. Current state and execution boundaries

**Status as of 2026-10-03: first IS completed; OOS technically blocked; sealed pipeline unfinished.**

- Pre-results hypothesis commit: `63664eb`, 2026-10-03 13:13:05 Eastern. The user subsequently ran the first IS notebook.
- Review manifest: 16 transactions/14 buyers. The primary horizon has 13 finite event observations and 88 ordinary observations. Portfolio: 12 closed positions and two skipped priced signals.
- Portfolio calendar: 502 sessions, 12 NAV gaps, 485 valid adjacent returns. Known final NAV $987,967.19; total net return -1.2033%; endpoint annualized return approximately -0.6059%. Full-window path metrics remain unavailable. These are proxy results, not proof of stable edge or executable fills.
- `RUN_OOS=False` and `RUN_HOLDOUT=False`. Enabling `RUN_OOS` currently raises `RuntimeError`; `build_events` rejects dates outside the IS manual review. This is an implementation blocker, **not** a rule saying contestants may never evaluate OOS.
- First IS outputs and transactions must remain as the original record. Reporting corrections have been labelled separately. A new quote-based valuation or re-simulation would be a post-first-IS version, not an overwritten original result.
- Latest README/notebook repairs are local uncommitted edits. No final English PDF exists in the project. No completed final submission or judges' sealed test is claimed.
- Historical labels, static membership, nonrandom pricing coverage, issuer/date dependence, unmatched pooled control years and unmeasured execution/capacity remain limitations. Disclosure and synthetic tests do not eliminate them.
- The user authorized tasks 1 and 2: original NAV-gap audit and a maximum-two-case IS historical quote feasibility probe, plus read-only inspection of the open Databento account. Both audit and Massive probe are completed; see Section 8. This does not authorize uniform repricing or a new strategy run. Programmatic credential loading for authorized API authentication is permitted in memory only; never expose keys to the model, outputs or Git.
- Further strategy/valuation changes, new API scopes, real IS re-simulation and the eventual one-time OOS evaluation require the corresponding user authorization. Routine authorized rule-document maintenance does not require another confirmation. Autonomous overnight research remains paused.

## 6. Improvement queue — do not tell the user to run OOS now

| Work item | Useful work before OOS | Current dependency/status |
|---|---|---|
| Evidence and interpretation | Separate relative theta from absolute losses; document counterparty/mechanism alternatives, costs, missingness and concentration. | Existing IS evidence available; no new market fetch required. |
| Failure/variant record | Record the abandoned H6 and all attempts, primary choices, fixed sensitivity and post-IS reporting revisions. | Can be assembled from existing history without OOS. |
| Statistical inference | Add a separately declared issuer/date-dependence robustness analysis and state small-sample limits; do not change the primary or select favorable subsets. | Proposal/review first; reuse existing IS tables if authorized. |
| Valuation and costs | Original gap audit and two-case Massive quote probe passed. Next propose uniform quote quality/age/synchronization rules, then consistently value the original ledger. | Uniform valuation and its larger data scope still need approval; no automatic re-simulation or restored skipped positions. |
| Risk and capacity | Complete single-position loss, net risk exposure, factor/correlation, tail/regime, and dollar-capacity evidence alongside all-leg participation and measured cost assumptions. | Section 9 records source-level gaps. New prices/factors, changed risk rules or new simulations still need scope approval. |
| General window implementation | Implement one reproducible economic eligibility rule, public-information clocks, calendar handling and output schema for arbitrary start/end inputs. Test with synthetic fixtures first, without reading OOS prices or records. | Required development still unfinished; cannot be replaced by copying the IS whitelist. |
| OOS readiness gate | Review/freeze the final executable rule and data/valuation convention, validate with fixtures/IS and present the concrete command and scope for approval. | Only after the previous blockers are resolved. |
| One-time OOS | After readiness and explicit approval, run 2026 Jan–Aug once; report every horizon/coverage/net result, good or bad. | Not runnable now; do not tell the user merely to flip a flag or use Run All. |
| Final note/reproduction | Draft the English note around honest findings, maintain sources/AI-use/logs, verify headline reproduction and package license-safe public code. | Drafting can start now; final OOS/sealed-readiness claims must wait for evidence. |
| Judges' sealed | Provide the same finalized date-parameterized pipeline. | Judges execute; we never inspect the sealed data. |

Fixing valuations can improve analytical/risk evidence but does not prove edge or guarantee points. Better implementation, honest uncertainty and reproducibility are the remaining goals; profit-directed parameter expansion is not a substitute.

## 7. Maintenance procedure

When the user mentions rules, read this file and the relevant notebook/README implementation, not the websites by default. Distinguish **required**, **chosen**, **implemented**, **tested**, **blocked**, **reserved** and **proposed**. Update current state only after observing completion; never convert a proposal or API entitlement assumption into a completed result. Retain dated rule conflicts and original pre-results design. Browse only for a justified missing/changed rule, then update this one reference. Do not create another competing rules document.

## 8. Supplemental data — verified feasibility and proposed extensions

**Verified on 2026-10-03: original gap audit and two authenticated Massive quote requests completed under the user's task-1/task-2 authorization.** Databento was inspected through the user's logged-in browser; no Databento data job, paid order, API-key action or download was submitted. No portfolio valuation or strategy rerun occurred. Two successful Massive cases do not establish full-ledger coverage.

| Priority | Input and proposed use | Scope and limitation |
|---|---|---|
| 1 | Historical option bid/ask, sizes and genuine quote-update timestamps; Massive quotes first, Databento OPRA as an alternative. | The approved two-case feasibility probe passed. Next declare the uniform original-ledger scope and valuation rules for approval. Availability does not guarantee all-gap closure or executable fills. |
| 2 | Contract definitions, multiplier/deliverable and correction-aware trades/volume. | Map exactly the original contracts; check corporate actions and every leg/side. Quote size and daily volume do not establish scalable multi-leg execution. |
| 3 | Actual underlying prices, dividends and splits/corporate actions. | Diagnose parity/basis and financing/dividend effects. A real-share covered-call study is a separately labelled extension, not a silent replacement for the Massive synthetic-stock baseline. |
| 4 | IS market/industry benchmarks and Kenneth French daily factors. | Supplement risk attribution once NAV is adequate; equity-factor regression cannot fully explain nonlinear short-call risk or prove an event-specific premium. Do not download a complete factor file containing reserved dates without an IS filter at ingestion. |
| 5 | SEC filings/acceptance headers and issuer IR releases available by the decision time. | Validate first-public information, agreement novelty, duplicate transactions and concurrent news. This improves signal provenance, not option-price coverage. |

Massive option aggregates use eligible trades; absence of a bar can mean no qualifying trade, rather than a failed request. A different vendor's trade bars therefore do not necessarily solve the gap. The existing credential successfully accessed historical quotes for the two original IS puts below. This verifies that scope only, not all contracts/dates or a future window. SIP timestamps are receipt times, not proof of exchange-side update time or simultaneous execution.

Databento `OPRA.PILLAR` supplies consolidated US equity-option data and point-in-time definitions. For quote-age checking, prefer genuine quote updates such as `cmbp-1`, or a documented last-quote-update field. `cbbo-1m` is an interval snapshot and may carry forward BBO when only a trade occurred. Its `ts_recv` is the interval end and `ts_event` refers to the last trade; neither proves the BBO was freshly updated. Trade-triggered `tcbbo` also does not recover quote-only activity.

Before a paid download, declare exact contracts, IS-only dates, schema, cutoff and permitted cost, and obtain a request-specific estimate using Databento's documented `metadata.get_cost` or portal estimate. Do not download whole chains, full OPRA history or live subscriptions for this daily-marking probe.

A proposed quote valuation must declare cutoff, quality/age rules, missingness handling and three-leg synchronization before viewing its effect on returns. If approved, apply the same method to every original holding day, retaining the original positions and cash flows. Cost/return comparisons also need the same standard for event and ordinary observations. Midpoints are valuation proxies; directional bid/ask crossing is an execution-cost scenario, not a guaranteed simultaneous fill. Preserve the first IS version and report any new quote-based study as post-IS sensitivity. Do not restore skipped positions without separately approved re-simulation.

Additional data cannot create independent events, remove static-TOP100 survivorship, fix the unseen-window classifier, supply OOS authorization, or establish that calls were mispriced. Better coverage may make evidence less favorable as well as more complete.

Direct sources:

- [Massive option quote endpoint](https://www.massive.com/docs/rest/options/trades-quotes/quotes)
- [Massive option aggregate construction](https://www.massive.com/docs/rest/options/aggregates/custom-bars)
- [Databento OPRA and point-in-time option definitions](https://databento.com/docs/examples/options/equity-options-introduction/using-parent-symbology-to-fetch-an-option-chain)
- [Databento CBBO fields and forward-fill conventions](https://databento.com/docs/schemas-and-data-formats/cbbo)
- [Databento historical request cost estimate](https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost)
- [Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- [SEC developer resources](https://www.sec.gov/about/developer-resources)

### Completed tasks 1 and 2: evidence and limitations

**Task 1 — original-run gap audit:** 502 sessions, 12 missing NAV sessions, 21 active-position days and 63 original three-leg checks. All 13 failing leg-day observations have an otherwise valid last daily-bar close older than the frozen three-session limit. They consist of TMO 3, CHTR 8 and UNP 2 failures; CHTR has two failing legs on June 6. Original contracts were recovered from the retained executed ledger and priced objects, without reselection. Original daily/ledger/cache-object hashes were identical before and after inspection. Exact intraday last-trade times were not retained and remain unknown.

**Task 2 — two-case quote probe:** each request covers 15:45 to 16:00 Eastern, end exclusive, on the original missing day. No retries, pagination, raw price output/storage, NAV filling, restored skipped positions or simulation occurred.

| Original failed put | Date | HTTP | Returned/in-range/two-sided positive noncrossed quotes with positive sizes | Latest SIP quote age to close |
|---|---|---:|---:|---:|
| `O:TMO250620P00540000` | 2025-03-21 | 200 | 392 / 392 / 392 | 13.645950976 seconds |
| `O:CHTR250919P00420000` | 2025-06-04 | 200 | 228 / 228 / 228 | 6.606809273 seconds |

Both responses were below the 10,000 limit with no next page. No `conditions` field was returned: condition validity remains unverified. These are coverage diagnostics, not tradable fills, midpoint valuations or a newly frozen freshness threshold. A 15-minute interval with no update would not itself prove that no standing quote exists.

**Databento backup:** the logged-in OPRA page states that historical access does not require a live-data license. The request builder lists `CMBP-1` quote updates from 2023-03-28. An unsubmitted TMO-parent, full-chain, March 21 2025 one-day draft showed 593.6 MB and an estimated $0.09 at $0.16/GB. This is not the estimate for an exact-contract 15-minute request and is not a download/entitlement success. The selection was cleared; the final page shows zero products and a disabled submit button. Account credit balance, exact-contract Databento coverage and a request-specific small-scope cost remain unverified. Massive works for both probes, so there is no present need to buy the full-chain draft or a live subscription.

**Browser boundary incident:** the vendor's TMO product-detail page automatically displayed a default latest-chain snapshot dated 2026-09-24 before the IS date filter was located. Its price values were not used for hypothesis selection, strategy/parameter changes, returns or NAV. No reserved-window study was run. This incidental non-IS visibility is recorded rather than claiming that every displayed vendor field was IS-only. Subsequent explicit request scopes were confined to 2025 and no Databento data request was submitted.

Private artifacts are retained in the chat workspace `work/`: `first_is_gap_audit.json`, `first_is_gap_audit.csv`, `first_is_gap_audit.md`, `first_is_quote_probe_manifest.json`, `first_is_quote_probe_results.json`, and the sanitized standalone probe source. They are outside the WSL submission repository and contain no raw quote prices or credentials. The original contract mapping should be retained in future reproducible ledger output.

### Next proposed task — not executed or frozen

Declare a quote-based valuation sensitivity before additional retrieval: Massive-first source precedence, genuine timestamps, quote-quality and age rules, consistent three-leg cutoff, no look-forward, invalid/missing quote treatment and corporate-action handling. Obtain approval for the complete original-position-day scope before retrieval/revaluation. Preserve original positions, entry/exit dates, cash flows, skipped signals and the first IS output; a valuation-only comparison must not claim a newly simulated entry/risk-decision path. Apply a common method rather than switching only favorable days/legs. If a future execution-return study changes marks/costs, use the same method for event and ordinary observations and declare it as a separate post-IS sensitivity.

With a complete valid calendar NAV path, report full-window Sharpe, volatility, daily-close maximum drawdown, equity curve and frozen/annualized turnover. Do not fill remaining gaps with zero or stale prices. Supplement with all-leg spreads/sizes/capacity, issuer/date dependence, concentration and honest failed-idea/variant logs. These improvements support analytical rigor and realism; they do not establish an event-specific option premium or guarantee a competition score. General-window classification and reproducibility remain separate unfinished tasks. OOS remains blocked and requires its own readiness gate and authorization.

## 9. CH01--CH08 live chapter audit

**Verification scope, 2026-10-03:** read the current official main-track page in the connected browser after the text-fetch tool could not open it. Read all eight chapters, all nine expanded CH06 pitfall cards and all eight CH08 note-detail panels. Also observed CH09's cap and CH10's submission requirements in the same page. No synthetic lab, OOS button, live/paper trade or project backtest was executed. Browser demos, selected rubric scores and checklist counts are not project results or organizer grades. The standalone Participant Brief is still unavailable; its precedence and the existing deadline/page-limit conflicts remain recorded above.

The earlier short improvement list was a useful grouping, not an exhaustive chapter-level acceptance checklist. This audit adds explicit acceptance items without changing the pre-results hypothesis or authorizing execution.

| Chapter / direct source | Interpretation | Current project assessment and remaining evidence |
|---|---|---|
| [CH01 Overview](https://www.gqhacks.com/tracks/systematic-trading#st-mission) | Core research workflow and delivery requirements. | Pre-results hypothesis and first IS exist. Complete honest failures/variants, executable final pipeline, approved one-time OOS and final note/code agreement. |
| [CH02 Hypothesis](https://www.gqhacks.com/tracks/systematic-trading#st-hypothesis) | Explain the counterparty, economic mechanism, persistence, prediction and falsification before results. The four source tabs are alternative examples, not four mechanisms every strategy must claim. | Preserve the committed original. Clarify supporting and conflicting evidence and distinguish event-specific premium from ordinary short-volatility/equity exposure. Do not retrospectively rewrite the thesis as a prediction of observed results. |
| [CH03 Data](https://www.gqhacks.com/tracks/systematic-trading#st-data) | Data provenance, appropriate adjustments, missingness, survivorship and an untouched holdout must be addressed. | Add explicit instrument/frequency/date and adjustment policies, option multiplier/deliverable/corporate-action checks, pricing coverage and static-universe bias assessment. Quantify what the approved data can identify and state what it cannot; coverage/concentration statistics do not estimate the counterfactual survivorship return bias by themselves. Keep Massive's required TOP100. |
| [CH04 Webull starter](https://www.gqhacks.com/tracks/systematic-trading#st-webull) | An available starter and integration guide, not a requirement to replace Massive. The page allows any language and optional sponsor data. Paper/live examples are not scored. | No Webull account, API application, second repository, starter migration or live trading is needed for this project. Preserve applicable cost/holdout/reproduction principles. |
| [CH05 Backtesting](https://www.gqhacks.com/tracks/systematic-trading#st-backtest) | Lagged information, defensible net costs, doubled-cost stress and separate IS/OOS minimum metrics. Its synthetic trend lab is an illustration. | Finish uniform valuation coverage before complete-calendar Sharpe/volatility/drawdown/turnover. Justify commissions, spreads and slippage in units appropriate to each leg and declared capital. The existing premium haircuts are proxy assumptions, not measured execution. |
| [CH06 Pitfalls](https://www.gqhacks.com/tracks/systematic-trading#st-pitfalls) | Audit all nine failure modes and support robustness transparently. | Add skew and worst month to the complete-path risk report; retain issuer/year diagnostics and explain overlapping observations. Keep the attempted-variant log and full prespecified sensitivity. Time-ordered CV/walk-forward and Deflated Sharpe are possible enhancements, not proof of robustness or mandatory replacement of the fixed Massive split. |
| [CH07 Risk and capacity](https://www.gqhacks.com/tracks/systematic-trading#st-risk) | Assess loss and exposure limits, de-risking, factor/correlation and tail/regime risk, plus participation and a dollar capacity estimate. | Gross/name/industry and entry-pause controls exist, but net risk exposure, model-consistent worst-loss analysis, factor/correlation calculations, explicit crash/volatility stress and supported dollar capacity remain incomplete. A dollar AUM figure without all-leg execution assumptions is insufficient. |
| [CH08 Quant note](https://www.gqhacks.com/tracks/systematic-trading#st-note) | Cover summary, economic hypothesis, data/universe, methodology, results, risk, liquidity/capacity and limitations/next steps. | Write an English note with cited sources, trading frequency, execution assumptions, separate net IS/OOS evidence and failures. Trading is event-driven with fixed exits and daily monitoring; it is not daily rebalancing. Keep the two-page core pending the Massive notebook conflict; the main page requires at least 11pt and standard margins. Suggested section page budgets are not additional mandatory page allocations. |

### Source-level gaps verified in the existing notebook

Cell indices below are zero-based JSON indices and refer to static source inspection, not a new execution.

- **Skew and worst month:** no calculation of daily-return skewness or complete monthly portfolio returns/worst month was found. Add them only with a defined valid return sample; disclose short history and idle cash. A partial month must not silently become a complete month.
- **Factor and correlation evidence:** no OLS/factor-regression or factor/correlation exposure implementation was found. Cell 24 defines issuer influence and yearly theta diagnostics and cell 36 uses them; these are useful but do not replace factor/correlation analysis. CH07's requested factor check belongs on the main-track queue. With complete daily NAV, a declared factor diagnostic can test simpler explanations; sparse activity and few independent events still limit interpretation and nonlinear option risk remains.
- **Maximum loss:** cell 38's `max_loss_proxy_at_entry = max(debit, 0)` describes entry capital at risk. It is not a proven loss bound for the implemented premium-dependent exit costs, financing or early-assignment risks. Supply payoff assumptions and model-consistent loss/stress analysis rather than presenting this proxy as a guarantee.
- **Net exposure:** cell 38 explicitly describes `stock_value_less_short_call_liability` as marked position value, not option-delta-adjusted net exposure. Existing stock-gross limits do not establish a separate net-risk limit. Report the distinction and propose any added risk-control rule transparently; a new rule changes the experiment and requires approval/versioning.
- **De-risking semantics:** the drawdown gate pauses new entries at 10% and resumes below 5%; current positions keep their scheduled exits. Explain this accurately and evaluate its limitations. Do not describe it as forced liquidation or dynamic size reduction.
- **Frequency:** disclose event-triggered entry, fixed-horizon/expiry-capped exit and daily valuation/admission monitoring. Do not label daily valuation as daily rebalancing.
- **Data adjustments:** cell 18 requests option bars with `adjusted=false`. Nonstandard `shares_per_contract` values are filtered, but missing fields default to 100; this does not verify the full deliverable or actions during the holding period. A contract-specific split/deliverable/dividend audit remains. Do not switch an option adjustment flag blindly or mix adjusted stock prices with inconsistent strikes/contracts.
- **Dollar capacity:** cell 38 already contains `per_trade_entry_stock_gross_capacity`, derived from the bottleneck of one day's three-leg volume and a participation assumption. Preserve this existing proxy rather than claiming no dollar calculation exists. It still lacks a historical ADV-based and spread/depth/impact-supported scale estimate. No positive edge-based capacity can be asserted if costs erase the effect. Preserve the required universe and state that the counterfactual survivorship return bias remains unidentified by the present export.
- **Public clocks and event novelty:** the category language in `HYPOTHESIS.md` refers to first public agreement disclosure, while the entry paragraph specifically waits for the required 8-K text to become public. SEC acceptance is therefore a plausible operational proxy for that text, not proof of a contradiction in entry timing. Earlier issuer news and document availability/latency still need review to establish novelty and whether the pre-filing chain already reflected news. Disclose the two clocks without retrospectively rewriting the original hypothesis or claiming a demonstrated lookahead violation.
- **Failure/variant provenance and stale descriptions:** the grid definition is not a complete actual-run log. Retain attempted, failed, unavailable and unrun cases separately. Cell 0 still contains pre-first-run wording, and cell 36 uses a broad `TRADEABLE_PRICE_PROXY` label for non-pre scenarios; reconcile them with actual execution status and the narrower timestamp safeguards in cell 22 when finalizing documentation. A label does not validate executable fills.

### Massive cross-check for shared requirements

The live [Massive page](https://www.gqhacks.com/tracks/systematic-trading/massive) explicitly states the exception to the main holdout split. Its CH05 gives the 2024--2025 IS and 2026 January--August OOS configuration, and its submission section requires clean-kernel/API-key-only execution over supplied dates. Local original notebook Markdown cell 4 retains the stricter two-page instruction and all-horizon IS/OOS, uncertainty, baseline and sensitivity requirements. Cell 44 exposes date arguments, but cell 16 rejects non-IS dates before fetching: the interface exists and the general economic classifier does not. Neither flipping a flag nor copying the existing whitelist completes judges' unseen-window readiness.

### Acceptance levels and scope control

1. **Core required delivery:** original hypothesis provenance, transparent data/universe, implementable signals/sizing/costs, fixed IS/OOS separation, net minimum metrics, risk/capacity discussion, attempted variants and reproducible note/code submission.
2. **Explicit evidence guidance now tracked:** skew/worst month, factor regression/correlation, per-position loss/net exposure, tail/regime scenarios, supported dollar capacity and quantified bias/coverage limitations where identifiable. If reliable estimation is impossible, document the exact limitation; do not mark the item verified or manufacture a statistic.
3. **Illustrative or optional:** Webull starter/account/live simulation, the website's synthetic market or noise experiments, example lookbacks/years, volatility targeting and the capacity slider's particular square-root formula. They are not requirements to add a second strategy or recreate the web page.

The scope is still the committed Massive agreement-union covered-call study. Fixes and declared IS sensitivities can improve evidence, but cannot be presented as pre-results choices or profit-selected replacements. First-IS artifacts remain intact. Larger quote/factor retrieval, new valuation/risk simulations and OOS execution retain their existing approval gates; sealed data remains judges-only.

## 10. Current autonomous completion authorization

**2026-10-03, after the CH01--CH08 audit:** the user explicitly authorized autonomous iteration to task completion, including computer/API access, provided actions follow the competition rules and guard against bias. This newer authorization supersedes the historical task-by-task approval statuses in Sections 5--9. It permits scoped IS data-quality/valuation work, risk/statistical diagnostics, general-window implementation, testing, English-note preparation and the eventual one-time contestant OOS evaluation only after the documented readiness/freeze gate passes. It does not make an incomplete pipeline ready or permit OOS tuning.

The pre-results hypothesis and first IS evidence remain immutable. Changes are post-first-IS extensions, with their declaration and scope in [RESEARCH_LOG.md](RESEARCH_LOG.md). No secret or licensed raw-data publication, judges' sealed execution, profit-selected parameters, or messages/submissions to third parties are authorized by an implementation step. The previous overnight automation remains paused. Operational status in this section and the research log takes precedence over earlier snapshots; official competition rules above are unchanged.

## 11. Current evidence and execution status — verified update, 2026-10-03

This is the current status section of the maintained rules reference. Official requirements and conflicts in Sections 1–4 remain unchanged. This current evidence status supersedes outdated operational statements in Sections 5–9 for the completed versioned IS package. It does not rewrite the preregistered hypothesis or declare a completed submission. Read `RESEARCH_LOG.md` for dated changes, original artifacts and incidental-information disclosures.

**Status labels:** **Fulfilled** means the specified artifact/action is verified; **Conditional** means evidence exists with a material assumption or incomplete component; **Unresolved** means the required result/readiness has not been achieved. These are research status labels, not organizer scores. A fulfilled disclosure of a limitation does not remove that limitation.

### Version and readiness record

| Item | Status | Verified scope / remaining limitation |
|---|---|---|
| Pre-results hypothesis | Fulfilled | Commit `63664eb`, dated 2026-10-03 13:13:05 Eastern, precedes the user-run first IS. `HYPOTHESIS.md` remains unchanged. |
| Original clean-process reproduction | Fulfilled | Eleven audited table families agree with retained first-run outputs at declared numerical tolerances, including identities/outcomes, scoreboards, fixed sensitivity, doubled costs and portfolio/ledger. One timing-status annotation is a declared nonnumeric difference. This reproduces the legacy model; it does not certify its causal validity. |
| V2 chronological labels | Fulfilled | Uniform review of all nine originally excluded control-qualified groups corrected two future-only exclusions. Manifest `corrected_is_v2_clock_repair` was fixed before new corrected prices; original labels/results remain archived. |
| V2 corrected study | Fulfilled | The separate corrected IS study completed. Ordinary controls regenerate under the same seed/template algorithm, so differences are not attributable solely to the two restored events. Its uniform quote/volume/factor evidence must retain its own snapshot hashes and completion status. |
| V3 portfolio clock | Fulfilled repair; conditional execution | The protocol preceded evaluation; twelve synthetic causality tests and the saved-data replay passed. Decision at entry-session open uses previous-close cash, holdings, budget marks, NAV/drawdown and reservations. Current-day prices, closing exit proceeds and later outcomes cannot admit or resize an order. The ledger has 13 closed positions, two ex-ante skips and one open final position. All V2 event tables remain identical; actual execution remains a proxy. |
| Automatic economic classifier | Unresolved | Offline text extraction and actual NYSE calendar support exist, but complete exhibits, reliable acceptance/public clocks and fully automatic first-disclosure/concurrent-news review do not. Partial core-text facts are not equivalent to primary eligibility. |
| Contestant OOS | Unresolved | No deliberate OOS strategy/price/return/event study has run. The runtime remains blocked until all readiness gates pass. The latest autonomous authorization permits the eventual one-time evaluation, not bypassing readiness. Incidental visibility is separately disclosed in the log. |
| Judges' sealed window | Fulfilled access boundary; unresolved pipeline | Never executed by the contestant, as required. A complete date-parameterized API-key-only pipeline is still required for judges; an IS whitelist or all-boundary output does not satisfy it. |
| Two-page English note | Conditional | The English two-page note is generated, checked against 184 numerical/source identities, and rendered page by page at minimum 11pt with standard margins. It remains prominently draft/incomplete because OOS and unseen-window completion are unresolved. No accepted submission is claimed. |

### Main-track CH01–CH08 cross-check

| Official chapter | Status | Evidence and remaining work |
|---|---|---|
| [CH01 Overview](https://www.gqhacks.com/tracks/systematic-trading#st-mission): hypothesis → data → build/test → one-time OOS → note/code | Conditional | Hypothesis, IS execution and clean reproduction exist. Final OOS, general pipeline and submitted note/repo agreement remain unresolved. Modest/null evidence is acceptable; a large backtest is not the objective. |
| [CH02 Hypothesis](https://www.gqhacks.com/tracks/systematic-trading#st-hypothesis): counterparty, mechanism, persistence, prediction and falsification | Conditional | Written before results with a falsifiable net event-specific increment. Demand-based option pricing motivates a conjecture; no retained paper directly proves post-agreement buyer-call overpricing. Explain genuine risk compensation, earlier information absorption and stock/short-vol exposure. |
| [CH03 Data](https://www.gqhacks.com/tracks/systematic-trading#st-data): provenance, cleaning, adjustments, missingness, universe and reserved period | Conditional | Massive-source cache/manifests, original/corrected scope and missingness are retained. Supplemental entry/scope-end metadata and in-window actions are checked. Static TOP100 survivorship and retrospective-label availability are disclosed, not quantitatively eliminated. Complete unseen-window filing sources remain unavailable. |
| [CH04 Webull starter](https://www.gqhacks.com/tracks/systematic-trading#st-webull): optional implementation example | Fulfilled | Applicability reviewed. Massive starter remains the single project; no Webull account, second starter, live/paper trading or mandatory 5–15-year window is required. This means optional-example applicability is resolved, not that a Webull strategy was executed. |
| [CH05 Backtesting](https://www.gqhacks.com/tracks/systematic-trading#st-backtest): lagged inputs, net/doubled costs, separate IS/OOS metrics | Conditional | Fixed event/control methods, cost stress, complete-calendar metric guards and original reproduction exist. Legacy same-close-conditioned admissions are retained and separately repaired in V3 with lagged state; proxy fills remain limited. Premium haircuts are cost proxies; no measured fill/impact model or OOS result is supplied. |
| [CH06 Pitfalls](https://www.gqhacks.com/tracks/systematic-trading#st-pitfalls): nine biases and transparent robustness | Conditional | Full fixed grid, coverage, issuer/year/dependence, failure/extension logs and missing-metric disclosures are retained. V2 and standing-state analyses are identified as post-IS. OOS is pending; small dependent samples and static membership remain. No zero-bias claim. |
| [CH07 Risk and capacity](https://www.gqhacks.com/tracks/systematic-trading#st-risk): loss, exposure, de-risking, factors/correlation, tail/regime, participation/dollar capacity | Conditional | Fixed size/gross/name/industry controls, pause/recovery rules, additional moments, fixed ETF-proxy regressions, tail/payoff analysis and all-leg pre-entry volume/spread evidence exist for the audited scope. Prior-state admissions are implemented and audited in V3. Marked value is not delta exposure; debit is not a universal maximum-loss bound under premium-dependent costs. Sparse volume, uncertain size units and unmodeled execution prevent profitable scalable-AUM claims. |
| [CH08 Quant note](https://www.gqhacks.com/tracks/systematic-trading#st-note): summary, mechanism, data, method, results, risk/capacity, limits and citations | Conditional | The rendered two-page English draft covers these topics, all fixed-horizon IS uncertainty and AI-use disclosure. Numeric/source agreement and layout checks pass; separate OOS evidence and Devpost delivery remain unresolved. The core uses at least 11pt and standard margins; an appendix cannot carry omitted score-critical evidence. |

### Massive-specific cross-check

| Requirement | Status | Evidence and remaining limitation |
|---|---|---|
| Actual category-to-library-strategy link | Fulfilled | `acquisition_agreement OR merger_agreement` under one first-buyer definitive operating-control agreement definition; covered call is the sole primary. H6 completion is an abandoned/exploratory branch. Multiple tags do not authorize blending unrelated economic events or choosing a winning strategy afterward. |
| Static official TOP100 | Fulfilled | The required starter universe is preserved. Whole-market records inform discovery/coverage only. Historical membership and a survivorship-free denominator are not claimed. |
| IS dates | Fulfilled | Events/outcomes remain 2024-01-01..2025-12-31. Explicit December 2023 option feature warmup reproduces existing selection dependencies only; it is not an expanded event/outcome or sealed study. |
| All fixed horizons and expiry | Fulfilled | 1, 2, 3, 5, 10, 21, 42, 63 sessions and expiry retained, with unavailable/expiry-capped/window-fenced cases and counts. The primary remains `t0 + 21`; do not relabel it as uniformly 21 sessions after entry. |
| Ordinary-day comparison and stock baseline | Conditional | Same-ticker deterministic ordinary dates, original net increment and official covered-call gap retained. Controls are neither one-to-one matched nor proven news-free; V2 control realization changes. Relative theta is not absolute profit or causal alpha. |
| Uncertainty / independent observations | Conditional | Required intervals and issuer/year diagnostics plus overlap-component evidence exist. Bootstrap assumptions and very few dependence components are disclosed; raw row count is not an independent sample size. No interval demonstrates stable generalization. |
| Implied-versus-realized diagnostic | Conditional | The starter diagnostic remains available. Synthetic spot, horizons and proxy prices limit interpretation; it does not establish the specific sold call was overpriced or that post-news entry captures repricing. |
| Expiry, OTM, timing, horizon and category sensitivity | Fulfilled | All prespecified cells and unavailable outcomes retained. The 972 correlated reporting cells are not 972 independent discoveries. No post-IS winner replaces the primary. |
| Public-information timing | Conditional | Reviewed acceptance clocks and V2 objective correction exist. Pre-entry press releases and availability latency matter. General automatic clocks are incomplete, while V3 order/admission timing passed synthetic causality checks and a fixed-data replay. `pre` is a diagnostic. |
| Net realistic costs / liquidity / capacity | Conditional | Original/doubled premium haircuts and supplemental bid/ask/size/20-session volume screens are reported. Haircuts need not cover observed spreads. Three-leg quote states are indicative; financing, assignment, dividends, queue/impact and broker collateral are unmodeled. |
| Contestant OOS once, after freeze | Unresolved | 2026-01-01..2026-08-31 not evaluated. Documented readiness precedes execution; do not use the main track's general holdout split to replace the Massive dates. |
| Start/end interface, clean kernel, API key only | Unresolved | Controlled source extraction, transport and NYSE calendar are implemented and original IS reproduces cleanly. General eligibility cannot yet be recovered faithfully from available sources without manual review. A signature or successful IS run does not establish unseen-window readiness. |
| Judges-only sealed replication | Unresolved | No sealed data read/run. The finalized general pipeline must be handed to judges; their score cannot be predicted from current IS reproduction. |
| Clear two-page write-up and code agreement | Conditional | English PDF, allowlisted aggregates, source hashes and rendered layout are checked. Required OOS evidence and actual Devpost delivery remain unresolved. The notebook's two-page cap is stricter than the webpages' five-page allowance. |

### Nine-pitfall evidence ledger

| Pitfall | Status | Assessment |
|---|---|---|
| P-hacking | Conditional | Original primary and failed/null/unavailable evidence remain; V2/V3 and standing-state diagnoses are versioned after IS. Continue disclosing every attempted variant, not only the published grid. |
| Overfitting | Conditional | Fixed parameters and full neighboring grid remain. Small/dependent samples and uncertain event-specific mechanism limit confidence; no parameter search or profitable-event selection is justified. |
| Lookahead | Conditional | Two future-only classification exclusions corrected. Legacy current-close financial admission is separately repaired and tested in V3. Earlier issuer news and automatic public clocks still limit signal provenance. |
| Survivorship | Conditional | Static TOP100 limitation is stated. No counterfactual historical-membership return bias estimate is available; mandated universe is preserved. |
| Ignoring costs | Conditional | Net and doubled costs retained; spread/depth evidence reveals proxy limits. Real execution/impact costs remain unverified. |
| Leaking test set | Conditional | No deliberate reserved-window study; OOS/sealed transports blocked. Incidental unrelated browser/source information is disclosed and not used to set rules. |
| Misleading Sharpe | Conditional | Legacy incomplete paths retain unavailable full-path metrics. Standing-state full metrics are separate conditional diagnostics; idle cash/calendar denominator, skew, worst month and dependency limits are disclosed. |
| Regime dependence | Conditional | Year/concentration and fixed factor/correlation evidence exist for available paths. Two years and sparse positions cannot establish long-run regime stability. |
| Unrealistic capacity | Conditional | All three legs and integer contract screens examined; missing volume is not silently zero. Gross dollars are per-trade screens, not established strategy AUM or profitable capacity. |

### Submission and publication acceptance

| Item | Status | Required final check |
|---|---|---|
| One repository and dependency/reproduction instructions | Fulfilled | Existing starter repository with root `run_research.py` check/report/complete-is modes, pinned Python dependencies, setup files and source attribution. README matches the integrated three-version CLI. The completed V3 repair is distinguished from unresolved realistic execution and unseen-window readiness. |
| Public derived output | Conditional | Allowlisted exporter excludes raw licensed bars/quotes, private snapshots, contract identifiers, filing texts and credentials, and records hashes/numeric checks. Only allowlisted derived artifacts are exported. The executed notebook is privately archived, public outputs are empty and candidate files pass an explicit private-path/credential-pattern review. Pattern checks are not a universal secrecy or licensing guarantee. |
| Private sponsor cache | Fulfilled | `.env`, `.venv`, `.massive_cache`, responses/snapshots and detailed inputs remain ignored. Exact full-request hashes permit historical immutable-response reuse, not falsely claimed fresh data. |
| Hypothesis/version provenance | Fulfilled | Original commit, private first-run hashes, exact original reproduction and post-IS manifests retained. Later improvements do not move the original preregistration timestamp. |
| Two-page PDF | Conditional | The generated two-page English PDF has been visually reviewed with minimum 11pt and 0.75-inch margins. Its incomplete-study label remains; no submitted/accepted PDF is claimed. References/optional appendix treatment under Massive is not an automatic exemption. |
| OOS / all-horizon IS–OOS tables | Unresolved | Final OOS evidence absent for the documented readiness reason; do not insert IS values, select favorable dates or mark it complete. |
| Devpost and public repo delivery | Unresolved | Repo URL exists; the public candidate package and PDF/source match are checked. The final team list and actual Devpost submission are still outstanding. Preparing or pushing code is not a Devpost submission. |
| Deadline / page-limit precedence | Unresolved | Formal brief/organizer announcement governs. Verified webpages' 11:00 AM ET conflicts with supplied 10:00 AM Devpost deadline; prepare by 10:00 AM. Keep the stricter two-page core pending clarification. |

Main-track rubric remains five criteria × 10 points; Massive remains 30 hypothesis/novelty, 30 rigor, 20 sealed replication, 10 realism and 10 communication. They are separate scores. Criterion 5's four-point cap is conditional on unreproducible code or lookahead/OOS tuning; these status tables do not apply or predict a judge's cap/grade.

### References and inference limits retained for the English note

The retained bibliography was previously checked against primary publisher/author/official sources. This draft reuses that evidence record; it does not claim a fresh full-text review. Keep the following concise references and their scope limits in the final note/reference material. None directly proves positive buyer-agreement covered-call theta.

- Gârleanu, N., Pedersen, L. H., & Poteshman, A. M. (2009). *Demand-Based Option Pricing*. Review of Financial Studies, 22(10), 4259–4299. [DOI](https://doi.org/10.1093/rfs/hhp005). Supports a demand-pressure mechanism under constrained intermediation; does not identify post-agreement buyer-call overpricing.
- Israelov, R., & Nielsen, L. N. (2015). *Covered Calls Uncovered*. Financial Analysts Journal, 71(6), 44–57. [DOI](https://doi.org/10.2469/faj.v71.n6.1). Separates equity, volatility and timing components; not evidence of an acquisition-specific edge. Disclose the AQR affiliation.
- Chan, K., Ge, L., & Lin, T.-C. (2015). *Informational Content of Options Trading on Acquirer Announcement Return*. Journal of Financial and Quantitative Analysis, 50(5), 1057–1082. [DOI](https://doi.org/10.1017/S0022109015000484). Acquirer options can contain pre-announcement information; this does not validate entry after public disclosure.
- Barraclough, K., Robinson, D. T., Smith, T., & Whaley, R. E. (2013). *Using Option Prices to Infer Overpayments and Synergies in M&A Transactions*. Review of Financial Studies, 26(3), 695–722. [DOI](https://doi.org/10.1093/rfs/hhs119). Provides M&A value-information context; prior review used the publisher abstract, so do not attribute unchecked full-text findings.
- Ben-Rephael, A., Da, Z., Easton, P. D., & Israelsen, R. D. (2022). *Who Pays Attention to SEC Form 8-K?* The Accounting Review, 97(5), 59–88. [DOI](https://doi.org/10.2308/TAR-2019-0425). Motivates distinguishing information arrival from filing time; not a direct options-strategy result.
- Christoffersen, P., Goyenko, R., Jacobs, K., & Karoui, M. (2018). *Illiquidity Premia in the Equity Options Market*. Review of Financial Studies, 31(3), 811–851. [DOI](https://doi.org/10.1093/rfs/hhx113). Supports careful liquidity/cost interpretation; it is not specific to this M&A study.
- [SEC Form 8-K](https://www.sec.gov/forms/form8-k.pdf), [SEC EDGAR FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions), [Massive quote documentation](https://www.massive.com/docs/rest/options/trades-quotes/quotes), and [NYSE hours/calendar](https://www.nyse.com/markets/hours-calendars) support regulatory, timestamp, data-schema and session definitions. SEC acceptance is an operational clock, not proven exact first public visibility.

Retain the full source map, vendor/preprint affiliation disclosures and AI-use record privately or in an approved reference appendix. References support motivation and method; they cannot substitute for OOS, executable costs, a causal classifier, or independent evidence of the hypothesized premium. All score-critical interpretation remains in the two-page core.
