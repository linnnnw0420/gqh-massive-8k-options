# V3 causal portfolio protocol — fixed before evaluation

Recorded 2026-10-03 20:38:28 UTC. This is a post-IS implementation repair, not the original preregistration. Preserve the original V1 and corrected-label V2 studies, event statistics, selected contracts, cashflows and archived results. No V3 portfolio result was consulted to choose these rules. V3 does not change fees, economic direction, event screen, universe, option selection, quantities or exit schedule.

## Decision clock and inputs

The signal must be public by the open of its already prescribed first-full-session entry day. An order cannot have been submitted at the previous close when its filing first appeared today premarket. Therefore **decision/submission time is the entry session open; the financial input cutoff is the previous NYSE close**. The frozen reviewed signal is known by decision time, and the unchanged contracts were selected from the pre-public chain. Record signal time, decision time, previous-session financial cutoff and the fields used for each decision.

Use only cash after the previous session's executions, prior-close known open positions, prior-close NAV/peak/drawdown state, and selected-contract marks on or before that previous session. Keep the original maximum mark age of three sessions evaluated at the previous-session cutoff. No current-day close, intraday price, current closing-data availability, current-day volume, current closing exit credit or future outcome may affect admission or quantity. On the first study day, start with $1,000,000 known cash and no positions; selected-contract budget marks still require prior-session availability. Initial book state is not fabricated from a future mark.

## Precommitted admission

Candidates remain ordered by entry date, ticker and accession. Admit one contract under the unchanged cash budget, one concurrent position per ticker, 10% name / 25% industry / 100% total synthetic-stock gross limits, and drawdown pause at 10% with recovery strictly below 5%. Use the prior book, including positions scheduled to exit today: those positions' cash or exposure release cannot finance or enable today's admissions. Concurrent-ticker rejection also uses the prior open book, conservatively preventing same-close recycling.

For multiple signals on one day, reserve each admitted order's estimated debit and fee using the same prior-close marks. Update estimated available cash, estimated NAV after fees and estimated name/industry/gross exposure for subsequent same-day decisions. These estimates do not use actual later fills. Prior book/selected-contract missing marks or unknown cash block new orders explicitly. No actual closing price may retrospectively reject, resize or cancel an admitted order.

## Execution and missing values

Execute precommitted entries and prescribed exits using the original closing daily-bar proxy, synthetic parity and 5% premium haircut for each of the three legs on each side. Scheduled exit remains `t0 + 21` sessions, capped at expiry. Actual holding length can differ from 21. Exit bookkeeping may occur before entry bookkeeping, but today’s realized exit proceeds never affect today's already committed decisions.

If a committed entry cannot be priced under the unchanged mark rule, keep one committed contract as **UNPRICED_EXECUTION**. Do not describe it as an economic rejection or assume the order did not fill. Entry cash becomes unknown, NAV remains unknown and later new orders fail closed. If its fixed exit can be priced, record that credit separately without inventing the missing entry debit; uncertainty is not erased. A missing fixed exit remains UNRESOLVED_EXIT and blocks later orders, with no later favorable exit substitution.

Actual fills can breach the ex-ante cash/exposure budget because marks move. Record the breach, retain the committed quantity and cashflow, and disclose any negative cash as an unfinanced execution-feasibility failure. Do not filter the trade retrospectively or imply broker acceptance. Today’s drawdown and unknown-mark state first affect the next session's orders. Positions whose fixed exit is after study end remain open and marked only inside the window; no fabricated closing liquidation. All daily returns retain idle cash and unavailable NAV observations.

## Scope, reporting and remaining assumptions

This implementation accepts only the existing 2024–2025 IS outcome window. The local exchange calendar may describe later scheduled exits; no price after the window is read. Prior-session December 2023 feature marks are permitted only under the separately documented feature warmup. No OOS, sealed data, API, new event statistics, new contracts, ranking or parameter search is part of this repair.

Keep compatible daily/ledger/metric/annual/capacity/breach output keys and add an order-decision audit with inputs, timestamps, reservations, admission reason and committed quantity. Current closing valuations are reporting/execution inputs, not signal inputs. Capacity volume remains retrospective and never gates orders. Max-loss entry-debit fields remain only nominal proxies, not mathematical worst-case loss bounds under the uncapped premium-cost model.

Daily last-trade marks can be stale and asynchronous and are not executable closing NBBO. Prior-close budget marks may be especially imprecise. A submission at open targeting the close assumes operational ability to transmit and maintain an order; broker collateral, cash settlement, limits, liquidity, actual spreads, assignment and dividends remain unmodeled. V3 removes closing-price-conditioned admission but does not establish fully executable trading or eliminate event-observation/sample biases. A null or worse V3 result must be retained.
