# GQH / Massive — maintained competition reference

Last official verification: October 3, 2026, Systematic Trading CH01–CH08 and Massive webpage/notebook. Read this file for existing rules rather than repeating searches. Refresh only a missing rule, conflict, organizer change or user request. Direct user instructions govern local execution permissions.

## Official sources and unresolved conflicts

- [Systematic Trading main track](https://www.gqhacks.com/tracks/systematic-trading)
- [Massive subtrack](https://www.gqhacks.com/tracks/systematic-trading/massive)
- Official starter notebook **What you submit**, preserved in Git history and the ignored cleanup archive; calculations extracted in strategy_defs.py.
- User-supplied participant brief and organizer statements. The full separate formal brief was not independently obtained.

Formal brief/organizer announcements govern main-track conflicts; notebook/organizer announcements govern Massive-specific conflicts. Webpages allow five pages but notebook says two: use **two core pages**, at least **11pt**, standard margins. Do not assume an appendix/reference exemption cancels the stricter notebook limit.

October 3 webpages showed October 4 11 AM Eastern for Devpost/code; earlier supplied brief/screenshots showed Devpost 10 AM/code 11 AM. Conflict remains unresolved. Prepare for **10 AM Devpost**, without claiming the brief changed.

## Binding main-track requirements

1. State and record the economic hypothesis before the first backtest: mechanism, counterparty, persistence and falsification. A later revision must be disclosed, not relabeled preregistered.
2. Cite clean data; define universe, missingness and corporate-action assumptions, and disclose survivorship/selection limitations.
3. Implement systematic signal, sizing, realistic costs and risk. Use information known before decision/fill; same-close signal/fill lookahead is prohibited.
4. Report net costs and doubled costs; distinguish measured spread/commission/impact from model haircuts.
5. Separate IS/OOS. Fix design, evaluate OOS once, report good or bad, never tune after seeing it. The sealed window belongs to judges.
6. Show separate IS/OOS net return/CAGR, volatility, Sharpe, maximum drawdown, turnover and equity curve. Overlapping event returns are not independent daily portfolio returns. Incomplete paths require explicit unavailable metrics, not invented fills.
7. Explain name/industry/gross/net limits, downside/tail exposure and de-risking; assess factors/correlation/regimes, liquidity, capital and capacity. CH07 recommends factor regression and dollar capacity evidence; unsupported items remain disclosed limitations, not claimed completed checks.
8. Disclose attempted ideas, failures and number of variants. Preserve null/negative/unavailable results rather than only the best cell.
9. Cite data, research and starter code; explain the contribution. AI use is allowed, but the team remains responsible and must understand the code.
10. One Devpost entry needs an English PDF and **public GitHub link**, both required. README setup/reproduction command, dependencies, relevant code and download instructions must reproduce headline numbers. List team members.
11. Never publish credentials, `.env`, licensed raw data, private snapshots/cache or raw notebook outputs.

Main scoring: **50**, ten each for Economic Foundation, Innovation, Risk Management Plan, Liquidity & Capital, Performance & Analytical Evidence. Criterion 5 is capped at four for failed reproducibility, lookahead or OOS tuning. Ties prioritize criterion 5 then economic foundation. No P&L leaderboard. Internal estimates are not organizer grades.

General main holdout is latest 20% of history or two years, whichever shorter. The Massive window rules **replace** it for this entry (verified Massive CH01/footer). The site's 5–15-year sliders and synthetic examples are not minimum history/OOS requirements. No minimum trade/event count was found; window compliance does not prove statistical adequacy.

## Additional Massive requirements

- One or more actual taxonomy categories; one primary library strategy. Allowed library: long call, covered call, protective put, collar, cash-secured put. Consistent tag union and deduplication are allowed; no requirement to rank all five.
- Official static TOP100; whole-market disclosure enumeration is not permission to expand the trading pool. Disclose static-universe survival and retrospective label availability.
- **IS 2024-01-01..2025-12-31; contestant OOS 2026-01-01..2026-08-31 once; sealed dates selected/evaluated only by judges.** Contestant OOS is not judges-only.
- Every horizon: **1, 2, 3, 5, 10, 21, 42, 63 sessions plus expiry**; retain expiry caps and unavailable observations with reasons.
- Ordinary-date comparison for the same names, uncertainty, implied-versus-realized diagnostic; show neighboring expiry, OTM, timing, horizon and category sensitivity without choosing a winner.
- Respect filing/public information lag. Pre-event is diagnostic; exact original news time may precede filing. Implied-v-realized alone does not establish an executable post-news premium.
- Keep Massive disclosures/options methodology; explain parity stock, daily last-trade marks, dividends, financing, assignment and execution limits. Cite any authorized supplemental source.
- Clean-kernel notebook/one built on starter must run on judges' supplied dates using a key and dates. An IS-only accession whitelist cannot substitute. Complete manual SEC inventories, our approval JSONs and exact manual-classifier equivalence were local additions, **not organizer requirements**; removed from this accepted delivery path.

Massive scoring: **100**, Hypothesis/Novelty 30, Analytical Rigor 30, Sealed Replication 20, Trade Realism 10, Communication 10. GQH forwards its ten strongest Massive entries for bonus judging. Main/subtrack scores are separate; both use the same Devpost submission. Sealed points cannot be claimed before judges' evaluation.

## Nine pitfalls

P-hacking, overfitting, lookahead, survivorship, ignored costs, test-set leakage, misleading Sharpe, regime dependence and unrealistic capacity must be addressed candidly. Retain version history; do not hide small dependent samples, same-day repricing or missing NAV. Unmeasured executable spreads/market impact cannot be called validated capacity.

## Accepted project definition and execution state

The full fixed V4 specification is in README.md. It uses literal acquisition_agreement/merger_agreement, accession union, date-only next-session close timing, inherited covered-call parameters and causal capital rules. It was accepted **after** the original IS. HYPOTHESIS.md remains the original pre-results record. No buyer/control/first-public claim is made for V4.

V4 event study covers unambiguous TOP100 tagged accessions; the capital ledger uses the inherited 14-name industry map and skips others. These are different estimands. Repeated transactions/issuers and overlapping windows mean row-bootstrap intervals are exploratory, not independent clustered certainty. No minimum sample is fabricated.

User approved simplification, revised IS, local English LaTeX/PDF creation and recoverable cleanup. **The owner executed the approved single contestant OOS; its journal is COMPLETE. Do not repeat or retune this experiment.** Public push/Devpost posting is not authorized. Paused automation stays paused. Keys may load in program memory for authentication only, never to logs/model/repo. No sealed evaluation.

The runner keeps source hashes and the single global OOS journal, without private SEC/approval prerequisites. Missing execution/valuation/coverage facts remain limitations. A draft paper or passing offline fixtures is not completed OOS or proven live execution.

Current verification: IS and contestant OOS COMPLETE with identical hashes of all ten computational files. The global one-shot journal is COMPLETE and matches the OOS manifest. Independent request-scope review found no sealed/out-of-window requests. The English two-page note includes all horizons, costs, controls, uncertainty and both derived curves. OOS theta is +3.38 pp, but event covered-call mean is -3.38%; the proxy contrast does not establish profitable or causal alpha. Capital metrics remain unavailable because of 130 IS and 6 OOS NAV gaps. This shortcoming must stay disclosed; do not claim all performance/capacity evidence is complete. Public push/Devpost posting remains unauthorized.
