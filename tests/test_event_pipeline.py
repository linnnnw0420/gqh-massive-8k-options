"""Synthetic-only event classification and offline exchange-calendar tests."""

import unittest
from dataclasses import replace

import pandas as pd

from event_pipeline import (EVENT_COLUMNS, EVENT_TAGS, VERSION, NYSEClock,
                            build_events, build_events_from_api,
                            extract_agreement, parse_sec_submission,
                            parse_items_evidence, sec_submission_url, validate_sec_url)

ACCESSION = "000000000125000001"
URL = "https://www.sec.gov/Archives/edgar/data/1/0000000001-25-000001.txt"
GOOD = ('On July 3, 2025, the Company entered into a definitive agreement to acquire '
        '100% of the outstanding shares of Target Software Inc. (the "Target") for $1 billion. '
        'Target Software Inc. is a leading software developer and provider of operating tools.')


def submission(text=GOOD, stamp="20250703090000", accession="0000000001-25-000001", exhibit=""):
    return (f"<SEC-HEADER>\n<ACCEPTANCE-DATETIME>{stamp}\nACCESSION NUMBER: {accession}\n"
            f"COMPANY CONFORMED NAME: Acquirer Holdings Inc.\nCENTRAL INDEX KEY: 0000000001\n"
            f"FILED AS OF DATE: {stamp[:8]}\n</SEC-HEADER>\n<DOCUMENT>\n<TYPE>8-K\n"
            f"<TEXT><html><p>Item 1.01 Entry into a Material Definitive Agreement.</p><p>{text}</p></html></TEXT>\n</DOCUMENT>"
            + (f"<DOCUMENT>\n<TYPE>EX-99.1\n<TEXT><p>{exhibit}</p></TEXT>\n</DOCUMENT>" if exhibit else ""))


def evidence(text=GOOD, stamp="20250703090000", accession=ACCESSION, exhibit=""):
    dashed = accession[:10] + "-" + accession[10:12] + "-" + accession[12:]
    url = "https://www.sec.gov/Archives/edgar/data/1/" + dashed + ".txt"
    return parse_sec_submission(submission(text, stamp, dashed, exhibit), url, accession)


def disclosure(package, tags=EVENT_TAGS, ticker="TEST"):
    return [{"tickers": [ticker], "cik": package.cik,
             "accession_number": package.accession_number,
             "filing_date": str(package.filing_date.date()),
             "filing_url": package.filing_url, "supporting_text": GOOD,
             "source_tag": tag} for tag in tags]


class TestClock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clock = NYSEClock.for_window("2025-01-01", "2025-12-31")

    def test_national_mourning_and_holiday(self):
        self.assertNotIn(pd.Timestamp("2025-01-09"), self.clock.sessions)
        self.assertNotIn(pd.Timestamp("2025-07-04"), self.clock.sessions)

    def test_halfday_clock_and_boundary(self):
        self.assertEqual(str(self.clock.session_close_time("2025-07-03")), "13:00:00")
        self.assertEqual(self.clock.public_signal_session("2025-07-03 12:59:59"), pd.Timestamp("2025-07-03"))
        self.assertEqual(self.clock.public_signal_session("2025-07-03 13:00:00"), pd.Timestamp("2025-07-07"))
        self.assertEqual(self.clock.pre_public_session("2025-07-03 13:00:00"), pd.Timestamp("2025-07-03"))

    def test_entry_open_is_strict(self):
        self.assertEqual(self.clock.first_full_session_close("2025-07-03 09:29:59"), pd.Timestamp("2025-07-03"))
        self.assertEqual(self.clock.first_full_session_close("2025-07-03 09:30:00"), pd.Timestamp("2025-07-07"))
        self.assertEqual(self.clock.next_public_open("2025-07-04 10:00:00"), pd.Timestamp("2025-07-07"))

    def test_timezone_equivalence(self):
        local = "2025-07-03T09:00:00-04:00"
        utc = "2025-07-03T13:00:00Z"
        self.assertEqual(self.clock.first_full_session_close(local), self.clock.first_full_session_close(utc))
        self.assertEqual(self.clock.acceptance_regime(local), "PREMARKET")

    def test_arbitrary_nonreserved_calendar_window(self):
        clock = NYSEClock.for_window("2030-01-01", "2030-01-31")
        self.assertEqual(clock.public_signal_session("2030-01-02 16:01:00"), pd.Timestamp("2030-01-03"))


class TestSourceAndClassification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clock = NYSEClock.for_window("2025-01-01", "2025-12-31")

    def build(self, packages, raw=None, **kwargs):
        return build_events(EVENT_TAGS, "2025-01-01", "2025-12-31", ["TEST", "GOOGL"],
                            raw if raw is not None else [row for p in packages for row in disclosure(p)],
                            {p.accession_number: p for p in packages}, self.clock, **kwargs)

    def test_sec_provenance_and_public_exhibit(self):
        package = evidence(exhibit="Target Software Inc. provides software.")
        self.assertEqual(package.accepted_at.hour, 9)
        self.assertEqual(package.company_name, "Acquirer Holdings Inc.")
        self.assertTrue(package.complete_submission)
        self.assertEqual(len(package.public_exhibits), 1)

    def test_invalid_provenance_and_wrong_accession(self):
        for url in ("https://example.com/Archives/edgar/data/1/a.txt", URL + "?apiKey=invalid", "http://www.sec.gov/Archives/edgar/data/1/a.txt"):
            with self.assertRaises(ValueError):
                validate_sec_url(url)
        with self.assertRaises(ValueError):
            parse_sec_submission(submission(), URL, "000000000125000099")

    def test_partial_index_identity_does_not_invent_acceptance(self):
        candidate = {"accession_number": ACCESSION, "cik": "1", "filing_date": "2025-07-03",
                     "form_type": "8-K", "filing_url": URL, "items_text": GOOD}
        index = {**candidate, "issuer_name": "Acquirer Holdings Inc."}
        package = parse_items_evidence(candidate, index)
        self.assertIsNone(package.accepted_at)
        self.assertFalse(package.complete_submission)
        result = self.build([package])
        self.assertTrue(result.empty)
        self.assertEqual(result.attrs["classification_audit"].iloc[0].reason, "COMPLETE_SEC_BODY_AND_EXHIBITS_MISSING")
        with self.assertRaises(ValueError):
            parse_items_evidence(candidate, {**index, "filing_date": "2025-07-07"})
        self.assertEqual(sec_submission_url("https://www.sec.gov/Archives/edgar/data/1/" + ACCESSION + "/main.htm", ACCESSION), URL)

    def test_explicit_eligible_and_legacy_schema(self):
        package = evidence()
        result = self.build([package])
        self.assertEqual(len(result), 1)
        self.assertEqual(list(result.columns), EVENT_COLUMNS)
        self.assertEqual(result.iloc[0].target, "Target Software Inc")
        self.assertEqual(result.iloc[0].source_tags, tuple(sorted(EVENT_TAGS)))
        self.assertIsNone(result.iloc[0].accepted_at.tzinfo)
        self.assertFalse(result.attrs["equivalent_to_manual_IS_review"])
        self.assertEqual(result.attrs["classifier_version"], VERSION)

    def test_alias(self):
        package = evidence()
        result = self.build([package], raw=disclosure(package, ticker="GOOG"))
        self.assertEqual(result.iloc[0].ticker, "GOOGL")

    def test_seller_update_nonbinding_and_minorities(self):
        cases = [
            (GOOD.replace("to acquire", "to sell"), "SELLER_SIDE"),
            (GOOD.replace("a definitive agreement", "an amended definitive agreement"), "UPDATE_OR_HISTORICAL_REFERENCE"),
            (GOOD.replace("a definitive agreement", "a non-binding letter of intent"), "NONDEFINITIVE_PROPOSAL"),
            (GOOD.replace("100% of the outstanding shares", "a minority interest"), "NO_NEW_CONTROL"),
        ]
        for text, reason in cases:
            with self.subTest(reason=reason):
                package = evidence(text)
                result = self.build([package])
                self.assertTrue(result.empty)
                self.assertIn(reason, result.attrs["classification_audit"].reason.tolist())

    def test_operating_or_control_not_inferred_from_tag(self):
        package = evidence(GOOD.replace("a leading software developer and provider of operating tools", "a legal entity"))
        result = self.build([package])
        self.assertTrue(result.empty)
        self.assertEqual(result.attrs["classification_audit"].iloc[0].status, "boundary")

    def test_target_context_not_unrelated_buyer_boilerplate(self):
        text = GOOD.replace("Target Software Inc. is a leading software developer and provider of operating tools.", "Acquirer Holdings Inc. is a software developer.")
        # Separate paragraphs prevent buyer boilerplate from being target evidence.
        text = text.replace("Acquirer Holdings", "</p><p>Acquirer Holdings")
        self.assertEqual(extract_agreement(evidence(text))[0], "boundary")

    def test_soft_wraps_and_explicit_controlling_stake(self):
        text = ('On July 3, 2025, the Company\nentered into an agreement with Seller Group to acquire an 85% controlling stake in its Target Delivery\n'
                'meal and grocery delivery business for $700 million in cash.\nThe acquisition remains subject to regulatory approval.')
        package = evidence(text)
        result = self.build([package])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.attrs["classification_audit"].iloc[0].evidence_spans["binding_basis"],
                         "EXECUTED_ACQUISITION_AGREEMENT_WITH_EXPLICIT_CONTROL")

    def test_legal_merger_survivor_and_full_filer_name(self):
        text = ('On July 3, 2025, Acquirer Holdings Inc. (the "Company") entered into an Agreement and Plan of Merger '
                'with Target Manufacturing Inc., a Delaware corporation ("Target"), and Merger Sub Inc. ("Merger Sub"), '
                'pursuant to which Merger Sub will be merged with and into Target, with Target surviving the Merger as '
                'a wholly owned subsidiary of the Company.')
        package = evidence(text, exhibit="Target Manufacturing Inc. is a manufacturer of medical equipment.")
        result = self.build([package])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0].target, "Target Manufacturing Inc.")

    def test_target_defined_as_company_does_not_make_it_filer(self):
        text = ('On July 3, 2025, Acquirer Holdings Inc., a Delaware corporation ("Buyer"), entered into a Stock Purchase Agreement '
                'with Target Manufacturing Inc., a Delaware corporation (the "Company"), pursuant to which Buyer will acquire '
                '100% of the outstanding shares of the Company. Target Manufacturing Inc. is a manufacturer.')
        result = self.build([evidence(text)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0].target, "Target Manufacturing Inc.")

    def test_post_entry_news_2025_premarket_regressions(self):
        for initial, after in (("20250506082108", "20250507080000"), ("20251205073107", "20251208080000")):
            day = pd.Timestamp(initial[:8])
            body = GOOD.replace("July 3, 2025", day.strftime("%B %d, %Y"))
            first = evidence(body, initial)
            other = evidence("The Company announced financial results for the quarter.", after, "000000000125000002")
            result = self.build([first], screening_documents=[other])
            self.assertEqual(len(result), 1)
            self.assertEqual(result.iloc[0].entry_day, day)

    def test_independent_news_and_transaction_eps(self):
        for news in ("The Company announced financial results for the second quarter.",
                     "The Company updated full-year financial guidance.",
                     "The Company reaffirmed full-year financial guidance.",
                     "The Company declared a quarterly dividend.",
                     "The board authorized a new share repurchase program.",
                     "The Company also entered into an agreement to purchase $300 million in newly issued ordinary shares of Seller.",
                     "The Company reiterated its previously announced repurchase authorization."):
            with self.subTest(news=news):
                result = self.build([evidence(exhibit=news)])
                self.assertTrue(result.empty)
                self.assertTrue(result.attrs["classification_audit"].iloc[0].reason.startswith("INDEPENDENT_"))
        for news in ("The acquisition is expected to be accretive to earnings per share.",
                     "During 2024, the Company bought shares under its previously announced repurchase authorization."):
            self.assertEqual(len(self.build([evidence(exhibit=news)])), 1)

    def test_pre_entry_screen_and_post_entry_news(self):
        package = evidence(stamp="20250703094500")
        before = evidence("The Company announced financial results for the quarter.", "20250707120000", "000000000125000002")
        after = evidence("The Company announced financial results for the quarter.", "20250707160001", "000000000125000003")
        self.assertTrue(self.build([package], screening_documents=[before]).empty)
        self.assertEqual(len(self.build([package], screening_documents=[after])), 1)

    def test_duplicate_tags_and_later_initial_wording(self):
        first = evidence()
        later = evidence(stamp="20250707090000", accession="000000000125000002")
        result = self.build([first, later])
        self.assertEqual(len(result), 1)
        self.assertIn("DUPLICATE_BUYER_TARGET_SIGNING_DATE", result.attrs["classification_audit"].reason.tolist())

    def test_initial_mixed_event_not_cleaned_by_later_duplicate(self):
        first = evidence(exhibit="The Company announced financial results for the quarter.")
        later = evidence(stamp="20250707090000", accession="000000000125000002")
        result = self.build([first, later])
        self.assertTrue(result.empty)
        self.assertIn("DUPLICATE_BUYER_TARGET_SIGNING_DATE", result.attrs["classification_audit"].reason.tolist())

    def test_prior_window_history_blocks_repeated_initial(self):
        first = evidence()
        later = evidence(stamp="20250707090000", accession="000000000125000002")
        result = self.build([later], screening_documents=[first])
        self.assertTrue(result.empty)
        self.assertIn("PRIOR_PUBLIC_DEFINITIVE_AGREEMENT", result.attrs["classification_audit"].reason.tolist())

    def test_remaining_shares_after_initial_tender_not_prior_control(self):
        package = evidence(exhibit="After the tender offer, the remaining shares will be acquired in the merger.")
        self.assertEqual(len(self.build([package])), 1)

    def test_seller_retained_minority_and_tender_second_step(self):
        text = GOOD.replace("100% of the outstanding shares", "an 85% controlling stake")
        for note in ("The Seller will retain a minority stake following completion.",
                     "After the tender offer, remaining minority shares will be acquired in the second-step merger.",
                     "The existing majority shareholder of Target Software will tender its shares."):
            self.assertEqual(len(self.build([evidence(text, exhibit=note)])), 1)
        self.assertTrue(self.build([evidence(GOOD, exhibit="The Company currently controls Target Software.")]).empty)

    def test_indirect_hundred_percent_business_purchase(self):
        text = ('On July 3, 2025, the Company entered into a share purchase agreement to indirectly acquire, '
                'through one of its wholly owned subsidiaries, 100% of the business and assets of Target Software Inc. '
                '("Target"), a leading software provider, for $1 billion.')
        self.assertEqual(len(self.build([evidence(text)])), 1)

    def test_missing_sec_evidence_is_retained_boundary(self):
        result = build_events(EVENT_TAGS, "2025-01-01", "2025-12-31", ["TEST"], disclosure(evidence()), {}, self.clock)
        self.assertTrue(result.empty)
        self.assertEqual(result.attrs["classification_audit"].iloc[0].reason, "COMPLETE_SEC_BODY_AND_EXHIBITS_MISSING")

    def test_fake_transports_api_key_only_interface_no_live_calls(self):
        package = evidence()
        calls = []
        def fake_api(path, params):
            calls.append((path, params))
            if path.endswith("disclosures"):
                return disclosure(package, tags=(params["tertiary_category"],))
            return [{"cik": package.cik, "filing_date": "2025-07-03", "accession_number": ACCESSION, "filing_url": URL,
                     "form_type": "8-K", "issuer_name": "Acquirer Holdings Inc.", "items_text": GOOD}]
        result = build_events_from_api(EVENT_TAGS, "2025-01-01", "2025-12-31", ["TEST"], fake_api,
                                       lambda url: submission(), self.clock)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(params["filing_date.lte"] == "2025-12-31" for _, params in calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
