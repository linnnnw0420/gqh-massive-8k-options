# V3 causal portfolio source and synthetic review

The protocol was written and reviewed before implementing or evaluating this version. No actual priced-event object, real observation, API transport, OOS/sealed data or result was executed by the independent implementer. The source is an explicit post-IS repair, not a new preregistration or a replacement for the preserved V1/V2 record.

## Interface

`simulate_causal_portfolio(priced, start, end, sector_by_ticker, *, namespace, clock, initial_nav=1e6, primary_horizon=21, otm=.05, haircut=.05, participation=.01)`

Pass the trusted extracted notebook's `runtime.namespace` and its local `runtime.clock`. The function uses only `_portfolio_marks`, `_portfolio_volume_rows` and `_portfolio_metric_block`; it never calls selection, pricing, event evaluation or a transport. It returns the original portfolio output keys and an additional `order_decisions` table. `config.mode` is `causal_portfolio_v3`.

Each decision records the public signal, current-session open submission time, previous-session closing financial cutoff, prior cash/NAV/peak/drawdown/open positions, missing-state reasons, prior selected marks/ages, same-day estimated cash/fee reservations, estimated exposures, admission reason and committed quantity. The function completes all of a day's admissions before reading that day's execution/reporting marks.

`UNPRICED_EXECUTION` retains one committed contract; it does not assume that the order failed to fill. Cash uncertainty remains permanent. A later fixed exit with known marks is `CLOSED_WITH_UNPRICED_ENTRY` and its credit is expressly conditional; it does not restore NAV or count as an observed execution cashflow. Capacity output distinguishes priced proxy entries from unpriced committed orders. A missing fixed exit is `UNRESOLVED_EXIT`, never repriced at a later favorable date.

## Verification

Twelve tests passed using synthetic fixtures and the isolated pure-definition loader with transports that raise if called:

- Today's selected price change leaves order decisions/quantity unchanged; actual cash and exposure breaches are retained.
- Today's other-position NAV gap cannot cancel an order based on known previous state.
- Today's scheduled exit proceeds cannot fund a new order, and its ticker cannot be recycled at the same close.
- Missing previous book state blocks a new admission explicitly.
- A prior-age-three/today-age-four execution gap preserves the committed order and permanent unknown cash.
- Same-day order reservations follow deterministic ticker/accession order and never consume actual later fills.
- Today's drawdown first pauses the following session.
- Missing prescribed exit is discovered on its date and never substituted with a later mark.
- Window-end positions remain open; calendar-only future exit dates do not permit future marks.
- Invalid public-entry clocks, outcome windows and frozen policy parameter changes fail closed.
- First-day starting capital and both audited timestamps are recorded correctly.

Command: `.venv/bin/python -m unittest test_causal_portfolio -v` in the private continuation directory. This command is synthetic only; it is not a study run.

## Remaining limits

The same daily closing last-trade proxy, three-session mark-age limit, asynchronous legs and premium haircut remain. Estimated prior-close budgets need not match current execution prices. Orders breaching actual cash or exposure limits are retained as explicit feasibility failures; no broker financing or actual fill guarantee is implied. Assignment, dividends, stock financing, adjusted deliverables, cash settlement and real order mechanics remain outside the original proxy. The repair does not cure event classification/observation bias, sparse independent samples, current TOP100 survivorship or weak economic evidence. Full-path risk metrics remain unavailable if committed execution or NAV is unknown.
