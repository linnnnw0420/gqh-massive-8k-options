# Pre-results Hypothesis

**Status:** Defined before any backtest; no results have been used to formulate this hypothesis.

## Category and strategy

The category is a TOP_100 acquirer's first public disclosure of a definitive agreement to acquire control of an operating business, identified by the union of Massive's `acquisition_agreement` and `merger_agreement` tags and screened under the prespecified event rules. The sole primary strategy is a covered call: a long stock exposure paired with a short out-of-the-money call.

## Hypothesis

Following a qualifying agreement disclosure, the covered call will earn a greater net incremental return over the stock exposure than the same covered call earns on ordinary days for the same tickers:

`theta = E[(covered call - stock)_net | event] - E[(covered call - stock)_net | same-ticker ordinary day] > 0`.

## Economic mechanism

Investors may buy calls to obtain leveraged exposure to expected synergies, strategic revaluation, or a possible competing offer. Yet a 21-session window may be too short for most integration benefits to appear, while financing, regulatory, and execution risks remain. If post-disclosure call premiums continue to reflect more near-term upside than is realized, writing the call may earn an event-specific premium relative to ordinary days. This is a conjectured mechanism, not an established fact: the market may reprice the information before entry, and the premium may simply compensate for genuine deal risk.

## Test and falsification

The primary contract uses the approved 90-180 DTE bucket, targets 120 DTE and 5% OTM, and is evaluated after 21 trading sessions. Entry is at the close of the first full NYSE session after the required 8-K text becomes public. The primary statistic is theta; the official event-minus-ordinary-day covered-call result and the stock baseline will also be reported. Net results use the approved 5%-per-side option-premium cost proxy, with a doubled-cost stress test.

A non-positive theta fails the directional prediction; an uncertainty interval spanning zero is inconclusive. If the result disappears under doubled costs or depends on one issuer, stale option marks, or the synthetic-stock proxy, the finding is fragile.

## Scope and limits

The study uses the static TOP_100 and the approved in-sample period. All official fixed horizons and required sensitivity checks remain in scope. Massive's historical labels support retrospective event identification; they do not establish that these labels were available in real time during the sample. The hypothesis does not predict that acquirer shares must rise or that a deal will close. The out-of-sample window remains untouched until the design is fixed and its evaluation is separately authorized.\n