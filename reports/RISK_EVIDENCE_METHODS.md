# Supplemental risk evidence: methods and interpretation

This report supplements the saved first IS run. It does not replace the committed hypothesis, select a new strategy, reprice trades, run the notebook, fetch data, or evaluate OOS. Source files are private. `risk_evidence_summary.json` contains aggregate derived evidence without raw option quotes, volumes, or contract symbols.

## Frozen estimand and current evidence

The primary remains the event-minus-ordinary-date difference in **covered-call incremental net return relative to synthetic stock**, using the 3–6 month expiry bucket, first-full-session close entry, 5% pre-event OTM selector, and 21-session horizon. It is not the covered-call portfolio's absolute return.

- 14 event candidates yield 13 finite outcomes, from 12 issuers; 109 ordinary-date candidates yield 88 finite outcomes, from 14 issuers. Unavailable observations remain counted.
- Primary theta: 0.01932297635, or **+1.9323 percentage points**.
- Original IID interval remains archived. Supplemental issuer-cluster resampling gives a **+0.9415 to +3.0794 percentage-point percentile range**.
- Connected overlapping holding intervals produce three clusters, with 78 of the 101 finite rows in the largest. Their resampling range is **−0.7184 to +2.2666 percentage points**.
- These are exploratory sensitivity ranges. Three interval components do **not** identify an effective sample size of exactly three: transitive overlap can connect positions that never overlap directly. Conversely, 101 priced rows do not imply 101 independent observations.
- Each bootstrap samples clusters with replacement and retains both event and ordinary observations together. Theta remains row-weighted within each draw. Issuer and date clustering are separate diagnostics, not simultaneous two-way-robust inference. Both use 2,000 draws and fixed seeds 20261003/20261004. No p-value or calibrated small-cluster coverage claim is made.
- Leave-one-cluster ranges are included. No issuer or period is deleted from the primary result on this basis.

## Cost sensitivity interpretation

The existing base event incremental mean is +1.0618%, versus −0.8705% on ordinary dates. Doubling the frozen haircuts gives +0.6257% and −1.3841%, respectively. Theta increases slightly to +2.0098 percentage points because the ordinary-date comparator is hurt more by costs. That increase is **not** evidence of cheaper implementation or improved absolute performance.

## Calendar metrics

The helper reindexes to the full declared NYSE session calendar, including the 2025-01-09 mourning closure. Missing dates and nonfinite NAVs are flagged, never filled or silently dropped. Returns use adjacent NAVs only. Idle-cash days remain in the series.

- Endpoint CAGR uses 252 sessions and the full declared period, consistent with the existing scorecard. A known endpoint does not certify the intervening path.
- Volatility uses sample daily standard deviation times square-root 252; Sharpe uses risk-free rate zero to match the frozen cash assumption.
- Skew is adjusted Fisher–Pearson daily skew and requires a complete valid return path.
- Monthly returns require every in-window NAV in that month plus a valid opening NAV. The full-window worst month is withheld if any month is invalid. Partial boundary months are explicitly in-window returns.
- Maximum drawdown requires the full nonnegative NAV path. Turnover remains two-sided gross traded dollars divided by full-calendar mean NAV; it is not annualized or halved. Initial-capital ratios are separate diagnostics.

The original path has **12 NAV gaps**, so full-path risk metrics and the factor regression remain unavailable. This is a data-validity result, not a poor-value suppression decision. A uniformly marked supplemental path may be analyzed separately when available; its valuation method and coverage must be identified.

## Factor attribution

The root task predeclared and retrieved 2024–2025 ETF data with no factor selection by fit:

1. Market proxy: SPY daily price return.
2. Value proxy: IWD minus IWF daily price returns.
3. Momentum proxy: MTUM minus SPY daily price returns.

These split-adjusted, dividend-excluding ETF returns are **not Fama–French research factors**, pure market-neutral style portfolios, or total-return data. They provide a limited diagnostic of style co-movement. The frozen cash rate is zero.

The regression covers 2024-01-03 through 2025-12-31 (501 sessions). January 2 is excluded only because no preceding 2023 ETF close was retrieved. Every later session is required. On the original portfolio path only 484 rows have complete portfolio/factor observations; the regression therefore fails closed rather than fitting to an advantageous subset.

`factor_evidence` uses an intercept and all three fixed proxies, with a Bartlett/Newey–West covariance and 21 lags tied to the primary holding horizon. The normal intervals are asymptotic descriptions. Few active episodes, nonlinear short-volatility exposure, proxy definitions, and missing dividends prevent treating a residual intercept as established alpha. A factor regression cannot validate the economic event mechanism by itself.

## Payoff, tail, and maximum-loss correction

The modeled position is a discounted strike bond plus one ATM call minus one same-strike put minus the selected OTM call. The scenario calculator matches that bookkeeping and the existing 5% premium haircut on every option leg, on entry and exit.

At expiry, its **gross** value per share is `min(S, U)`. Without trading costs, the downside loss is therefore bounded by the entry debit. With the notebook's **uncapped exit premium haircut**, however, the two call premiums grow approximately linearly with an extreme upside stock price. The gross terminal value remains capped, while assumed exit cost grows without bound. Consequently:

- Entry capital is not a strict finite maximum-loss bound under the current cost approximation.
- At a zero stock price, closing the deep-in-the-money short ATM put itself incurs an assumed haircut, producing a loss beyond entry debit.
- Unbounded modeled upside loss is an artifact of applying a percentage haircut to offsetting gross option premiums at arbitrarily high prices; it is not a claim that an ordinary fully covered call intrinsically has unlimited upside economic loss.
- Do not silently remove the artifact after seeing results. Preserve the base model, disclose its limits, and distinguish any subsequently justified execution model as a documented change or sensitivity.

The stress report uses original entry marks only and a fixed set of hypothetical spot/volatility states, including expiry values and instant volatility shocks. These are not future observations, forecasts, market-calibrated valuations, or changes to the frozen 21-session exit rule. Each actual entered position is stressed separately; summing those shocks is not a simultaneous portfolio scenario because entry dates differ.

The European scenario model excludes dividends, American assignment, exercise fees, financing spread, changed deliverables, real quotes and market impact. Its Greeks exclude the derivative of liquidation-cost assumptions. It cannot certify live-trading margin or loss limits.

## Variant disclosure

The saved grid contains 972 distinct cells and no duplicate cells: 108 category/expiry/entry/OTM configurations times nine fixed horizons. Of these, 243 are pre-filing diagnostics. All 972 have some finite theta, but that does not mean all candidate observations within them were priced. These cells are highly correlated and are not 972 independent hypothesis tests. Base and doubled-cost outputs both remain visible. Earlier rejected ideas and human design decisions still belong in the separate research log; this result table cannot reconstruct them.

## Literature retained for the final note

These references were already verified and bounded in the local literature evidence map. They motivate methods and competing explanations; none directly establishes the present post-disclosure event-specific net advantage.

- Israelov and Nielsen (2015), *Covered Calls Uncovered*: separate equity, volatility and timing components. [Author paper](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Covered-Calls-Uncovered.pdf).
- Gârleanu, Pedersen and Poteshman (2009), *Demand-Based Option Pricing*: limited arbitrage allows demand to affect prices, but this does not establish post-acquisition-signing call demand in our sample. [DOI](https://doi.org/10.1093/rfs/hhp005).
- Ben-Rephael et al. (2022), *Who Pays Attention to SEC Form 8-K?*: information can reach investors before the filing, challenging delayed-entry narratives. [DOI](https://doi.org/10.2308/TAR-2019-0425).
- Bargeron et al. (2014), *Disagreement and the Informativeness of Stock Returns*: acquisition announcements can increase uncertainty; higher premiums need not be mispricing. [DOI](https://doi.org/10.1016/j.jcorpfin.2013.11.014).
- Christoffersen et al. (2018), *Illiquidity Premia in the Equity Options Market*: option liquidity and implementation costs matter to measured returns. [DOI](https://doi.org/10.1093/rfs/hhx113).

The original reviewed evidence map distinguishes full-text, author-version and abstract-only access. Retain those limits rather than attributing unverified details to papers.

## Subsequent standing-state valuation sensitivity

After the two predeclared update-age screens left 37 and 36 NAV gaps, the root task recorded a separately justified same-session standing-NBBO diagnostic before calculating its metrics. It assumes the latest valid same-session state persists to a common close; it never retrieves a later observation, resurrects an earlier valid state, carries across sessions, changes original cashflows, or re-simulates admissions. This is explicitly post-coverage analysis and remains separate from the original results and strict screens.

Under that assumption the 502-session path is complete. An independent arithmetic implementation verified eleven reported quantities: net CAGR −0.6059%, annual volatility 0.7663%, rf=0 Sharpe −0.7892, maximum drawdown 1.6969%, daily skew −3.5188, worst month April 2025 at −0.6526%, total net return −1.2033%, and the three turnover ratios. Stock-reference turnover is 0.7296 times full-calendar mean NAV. These are conditional valuation metrics of the fixed legacy ledger, not proof of tradable fills or repaired risk-gate decisions.

The same predeclared three ETF proxies can be fit over all 501 regression sessions under this valuation assumption. The market-proxy beta is 0.0241 and correlation 0.4781; the small beta partly reflects substantial idle capital. The daily intercept is negative, and its asymptotic HAC interval includes zero. Neither style coefficients nor an intercept from sparse nonlinear option positions establishes event alpha. See `quote_supplement_summary.json` for the complete retained factor/correlation report, and `standing_metric_verification.json` for the independent arithmetic checks.

## Reproduction and validation

`risk_evidence.py` contains pure functions and a guarded IS-only reporting CLI. It reads the private saved first-IS snapshot; no strategy or API function is called. The output records the input SHA-256. Optional factor input must match the predeclared columns and every declared factor session exactly. Fourteen synthetic checks cover missing rows/month boundaries, invalid NAVs, exact factor coefficients, failed factor coverage, rank deficiency, put–call parity, the haircut loss artifact, overlap clustering and deterministic resampling.
