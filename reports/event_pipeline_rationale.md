# Event pipeline: implementation and honest readiness

This is an English implementation artifact in the private continuation workspace. It does not change the original notebook, hypothesis, Git history, first IS result, or any reserved data. The automatic extractor is `AUTO_TEXT_OPERATIONAL_V2_POST_IS`, an operational extension developed after the first IS run. It is not asserted to reproduce the original manual review.

## Implemented interfaces

- `NYSEClock.for_window(start, end)` generates an actual local XNYS schedule using `exchange_calendars`. It handles exchange holidays, the January 9, 2025 national mourning closure, July 3 half-day close, UTC/Eastern conversion, and the strict opening boundary. Premarket acceptance enters at the same session close; acceptance at or after the opening enters at the next session close. The signal day shifts after the actual session close, including half-days. Calendar generation reads no market observations.
- `parse_sec_submission(text, url, accession)` verifies complete SEC submission headers, accession, filer CIK/name, filing date and exact Eastern acceptance, and separates the current-report body from EX99 announcement exhibits and EX2 agreements.
- `sec_submission_url(url, accession)` constructs the ordinary complete-submission TXT URL when discovery supplies a primary-document URL. It accepts only validated HTTPS SEC Archives provenance.
- `parse_items_evidence(items, index)` joins Massive core Items text to the filing-specific EDGAR-index `issuer_name`. It does not substitute a current ticker name, a hand-built company map, an LLM key or a manual event whitelist. It deliberately returns no acceptance timestamp and `complete_submission=False`.
- `build_events(tags, start, end, universe, raw, evidence, calendar, screening_documents)` is offline and returns the existing notebook's event columns plus a classification audit. Its accepted tag union is exactly `acquisition_agreement + merger_agreement`. It deduplicates accession labels and explicit filer/target/signing-date transaction identities. An initially mixed announcement cannot become a new clean event through a later duplicate.
- `build_events_from_api(...)` accepts authenticated Massive and public SEC transport callbacks. Authentication, approved window guards, pagination manifests, secure caches and a stop-after-403 SEC transport belong to the caller. The module itself never reads credentials or sends a Massive key to SEC. It has no import-time network or notebook execution.

## Economic semantics and conservative boundaries

The extractor requires dated, current buyer agreement language; explicit new control; and an operating-business description connected to the named target. It recognizes legal merger-survivor recitals, executed majority/control purchases, purchase agreements, issuer subsidiary relationships stated in the filing, and vendor soft-wrapped sentences. It distinguishes a filer named Buyer from a target legally defined as Company. A label alone, transaction EPS accretion, financing, or unrelated buyer boilerplate does not prove operating-business control.

Explicit seller references, amendments/historical references, nonbinding proposals, minority/noncontrolling purchases, pure financing, and pure financial/nonbusiness assets are excluded when the text supplies that evidence. Unrecognized identities, control, operations or signing dates remain boundary cases. This deliberately cannot promise that every structurally complex transaction will be classified automatically.

Observed independent earnings, guidance changes or current reaffirmations, dividends/buybacks, and the previously reviewed separate seller-equity investment are screened only through entry close. A genuinely disclosed pre-entry competing proposal can be screened when its dated document is supplied; later events cannot affect the earlier entry label. Transaction-specific synergies/EPS estimates and ordinary operational partnerships are not new exclusion classes.

First-public IR history, vendor label publication lag, counterparties' earlier filings and the absence of unobserved news are not proved by this module. A supplied complete filing package is a necessary source condition, not a proof of exhaustive public-information coverage. Regex tests do not establish general classification accuracy.

## Actual bounded IS validation

The documented scope is all 56 unique union-tag accessions, including all 25 first-transaction candidates, the original 16 manual positives, the original nine excluded groups, and later/structural rows. No returns or later operating outcomes were used in extraction changes or validation.

The first SEC Archives request returned HTTP 403. Further SEC requests were stopped. An authorized fixed pass of 53 exact IS CIK/date queries to the official Massive Items-text endpoint recovered all 56 originals. A second fixed 53-query pass to the official filing index recovered filing-specific issuer names for all 56. Neither endpoint contains exact SEC acceptance or the full EX99 exhibit package.

Consequently, there are **zero complete SEC source packages, zero primary events admitted, and no valid complete-source confusion matrix**. The automatic primary path is **NOT READY**. Returning zero here reflects missing evidence, not an economic conclusion that no eligible events exist. The original 16 positives are not silently replaced by these boundaries.

The final offline partial-text extraction diagnostics are 6 explicit agreement-fact candidates, 48 boundaries and 2 explicit exclusions across 56 accessions. Among the 25 first candidates, 4 have explicit agreement/control/business facts and 21 remain boundary. These are extraction-stage diagnostics, not trade eligibility: BlackRock/GIP contains same-source earnings; AT&T/Lumen's outside exhibits may contain current buyback/guidance reaffirmations. All four still lack complete-source/exact-clock admission. The four extraction cases are BlackRock/GIP, BlackRock/Preqin, Uber/Trendyol and AT&T/Lumen. Of the original 16 manual positives, Preqin's core text is semantically explicit; the other 15 remain boundary on the available incomplete source or recognized legal-language coverage. This is a coverage/implementation mismatch, not evidence those original events were economically ineligible.

`is_event_text_semantic_replay.json` records every accession and all 25 first candidates, including source identity, missing semantic components, observed independent-news spans, old labels for comparison only, and saved acceptance/entry references explicitly marked not reverified. No original labels or first-run artifacts were overwritten. A core-Items-only classifier or a filing-date clock would be a different proposed operational experiment, not an equivalent repair of the frozen primary.

## Material original-review clock mismatch

The saved pre-results SEC index table records Uber/Trendyol accepted May 6, 2025 at 08:21:08 ET, and Netflix/WBD accepted December 5, 2025 at 07:31:07 ET. Both are premarket, so the frozen rule enters at May 6 and December 5 close. The next-day May 7 earnings or December 8 competing bid therefore cannot be an exclusion reason for those entries. The cached May 6 Uber core filing explicitly describes an 85% controlling operating-delivery-business purchase. The cached Netflix filing describes its signed December 4 agreement and December 5 announcement; Netflix's accessible primary December 5 announcement independently confirms the acquired operating businesses.

These are clock/label consistency corrections independent of returns. They invalidate those specific old exclusion rationales but do not prove that all other same-day information was absent. The independent audit is reviewing the remaining excluded groups and both correction cases. Any corrected IS computation must be a clearly named branch retaining the original first result and all changes; this module does not run it.

## Verification and sources

The offline suite passes 27 tests. It covers source-provenance conflict rejection, partial-source fail-closed behavior, buyer/target roles, legal recital and soft-wrap handling, seller-retained minority versus buyer control, indirect full-business purchases, concurrent-news cutoffs, duplicate/historical blocking, actual exchange-calendar edge cases, both 2025 premarket timing regressions, and a fake API transport with bounded requested end dates. This is implementation verification, not a stable-edge finding.

- [Massive EDGAR index schema](https://massive.com/docs/rest/stocks/filings/index): filing-specific `issuer_name`, accession, CIK, date and document URL; no acceptance/exhibits in the documented response.
- [Massive 8-K text schema](https://massive.com/docs/rest/stocks/filings/8-k-text): core Items text, rather than complete submission/exhibit content.
- [SEC Form 8-K](https://www.sec.gov/files/form8-k.pdf): item disclosures can incorporate an attached press release, so core Items alone can omit material announcement detail.
- [Netflix primary December 5, 2025 acquisition announcement](https://about.netflix.com/en/news/netflix-to-acquire-warner-bros): signed definitive buyer acquisition, operating businesses and premarket conference call. This mirror is useful for the specific economic scope, but does not replace a complete SEC header clock.

Remaining readiness work is complete-source and point-in-time coverage resolution, independent label/clock correction, and source-semantic validation across all IS groups. No OOS or sealed evaluation is justified by the synthetic test pass alone.
