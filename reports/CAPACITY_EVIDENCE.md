# Original-contract liquidity and capacity evidence

All calculations concern the twelve originally entered IS positions, their unchanged three option legs, original entry/exit dates and original one-contract sizing. This is retrospective implementation evidence. It neither changes admissions nor searches for profitable liquidity thresholds.

## Spread and endpoint quality

The code independently identifies actual entry and exit snapshots. Intermediate holding days are excluded from round-trip spread totals. Entry requires the ATM call ask and the ATM put/OTM call bids; exit reverses those directions. All three legs must pass the corresponding quote state and contract/action checks.

- Under the predeclared 60-second update-age screen: 21 of 24 endpoints are available, and nine of twelve trades have both endpoints. The observed three-leg half-spread subtotal is $5,350. The full-ledger round-trip spread estimate remains unavailable; $5,350 must not be represented as its total.
- Under the predeclared 300-second age sensitivity with the same 60-second inter-leg update span: the same 21 endpoints pass. The failed three endpoints are asynchronous by that screen.
- Under the separately declared post-coverage same-session standing-NBBO assumption: all 24 endpoints are available; their three-leg half-spread total is $5,800. This is a third diagnostic, not replacement of the two predeclared screens. Its source rationale and missing control/condition information are documented in `CONTINUATION_PROTOCOL.md`.

For the 60-second screen, the median half-spread is 0.712 times the 5% haircut applied to the same quote midpoints; the maximum is 2.635 times. Relative to the originally booked daily-trade-proxy haircut, the maximum is 3.250 times. Therefore the frozen cost model is not uniformly conservative at every observed endpoint, even though it can exceed typical spreads. Commissions, impact, queue priority, financing and any multileg execution risk are additional. Do not retrospectively reduce costs because an aggregate spread estimate is lower.

Displayed sizes are compared in the direction actually needed for each leg, using the smallest of the three. The raw bottleneck ranges from 1 to 412 and has median 20 across the available endpoints. The REST documentation's size-unit interpretation remains unresolved; these raw values are **not converted to a guaranteed number of contracts or dollars**. No endpoint has all quote-condition fields present in the returned data. Displayed size may change or be canceled; independently updated option legs need not fill together.

## Pre-entry volume

The window is precisely the twenty NYSE sessions preceding each original entry, never including the entry day's future volume. The same twelve positions, 36 original contracts and fixed 0.5%, 1% and 2% participation screens are used throughout.

- Only nine of 36 legs have valid volume observations on every one of the twenty sessions. Observed-bar coverage ranges from three to twenty sessions, with median seventeen.
- Only one of twelve positions has a strict twenty-session ADV available for all three legs.
- Missing daily price bars are never zero-valued NAV marks. For capacity only, a separate conditional convention treats absent volume bars as zero, while explicitly assuming the contract was listed and absence represented no eligible trades. Listing dates have not been established, so this is a sensitivity, not a proven complete trading history.
- Under that conditional convention, only one of twelve positions meets even the one-contract screen at each of 0.5%, 1% and 2% participation. This is evidence against casually claiming ample small-lot liquidity; it is not a retroactive rule for deleting the eleven other trades.
- The qualifying position's volume-screen gross notional is approximately $15,574, $31,148 and $62,297 at the three participation levels (one, two and four integer contracts). These are per-trade underlying-reference gross amounts, not strategy assets under management or demonstrated scalable profit. The other positions' conditional screens round below one contract.

ADV and displayed quotes test different limitations. A screen that passes one cannot substitute for missing evidence in the other. No combined volume-and-displayed-size contract limit is asserted while quote size units remain unresolved. No positive-edge capacity is inferred: the first portfolio's net return is negative and the event-specific incremental result remains uncertain.

## Files and reproducibility

- `capacity_evidence.py`: pure calculations plus saved-IS-input CLI.
- `capacity_evidence_summary.json`: public-facing aggregate results and source SHA-256 hashes.
- `capacity_details.private.json`: contract-level volume coverage and per-trade derived dollar/endpoint details; keep private with the source inputs.
- `test_capacity_evidence.py`: synthetic checks for full/missing/zero/invalid history, entry-volume exclusion, duplicates, all-leg bottlenecks, integer contracts, conditional size units, actual endpoints, trade-direction sizes, stale states, metadata, corporate actions and separate standing-state labeling.

This evidence strengthens disclosure and falsifiability. It does not establish execution readiness or remove the original data/strategy limitations.
