"""Synthetic payload validation and geometry checks; never creates a PDF."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from make_quant_note import validate_payload, read_public_nav, make_pdf

HERE = Path(__file__).resolve().parent


def fixture(folder):
    payload = json.loads((HERE / 'finalreport_payload.template.json').read_text())
    payload.update(generated_utc='2026-10-03T20:00:00Z', hypothesis_commit='test123',
                   correction_summary='A documented post-IS chronology correction restores two disclosures; unchanged rules and the original run are retained.',
                   cost_summary='Observed spreads challenge uniform conservatism of the haircut; fees and impact remain additional.',
                   capacity_summary='Incomplete volume histories and unresolved quote-size units prevent an executable dollar-capacity claim.',
                   factor_summary='Fixed price-only ETF proxies use HAC(21); sparse nonlinear positions and omitted dividends limit alpha interpretation.',
                   conclusion='The relative premium hypothesis remains exploratory. Better accounting is not stronger independent evidence or a tradable edge.')
    for study in payload['studies'].values():
        study.update(status='COMPLETE_IS_AGGREGATES', eligible_disclosures=16, n_event=13, n_ordinary=88,
                     theta=.01, iid_interval=[-.01,.03], issuer_range=[-.01,.03], date_range=[-.01,.03], original_nav_gaps=12)
        for row in study['horizons']:
            row.update(event_cc_mean=.01, ordinary_cc_mean=.02, cc_difference=-.01, theta=.01,
                       n_event=13,n_ordinary=88,cc_iid_interval=[-.03,.01],theta_iid_interval=[-.01,.03])
    return payload


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.payload = fixture(self.folder)

    def test_completed_aggregates_and_explicit_unavailable_portfolio_are_valid(self):
        self.assertIs(validate_payload(self.payload,self.folder),self.payload)

    def test_pending_corrected_numbers_refuse(self):
        for change in ({'theta':None},{'status':'PENDING'},{'issuer_range':[None,None]}):
            value = copy.deepcopy(self.payload); value['studies']['corrected'].update(change)
            with self.assertRaises(ValueError): validate_payload(value,self.folder)

    def test_horizon_primary_consistency_and_required_grid(self):
        for mode in ('mismatch','missing','wrong_difference'):
            value = copy.deepcopy(self.payload)
            if mode=='mismatch': value['studies']['corrected']['theta']=.02
            elif mode=='missing': value['studies']['corrected']['horizons'].pop()
            else: value['studies']['corrected']['horizons'][0]['cc_difference']=0
            with self.assertRaises(ValueError): validate_payload(value,self.folder)

    def test_actual_ten_decimal_serialization_residual_is_tolerated_without_edits(self):
        # Actual corrected five-session aggregate triplet, not new market data.
        row = self.payload['studies']['corrected']['horizons'][3]
        row.update(event_cc_mean=-.0195385614,ordinary_cc_mean=-.0199681338,cc_difference=.0004295725)
        before = copy.deepcopy(row)
        validate_payload(self.payload,self.folder)
        self.assertEqual(row,before)
        row['cc_difference'] += 2e-10  # Residual becomes approximately 3e-10.
        with self.assertRaisesRegex(ValueError,'official net difference'):
            validate_payload(self.payload,self.folder)

    def test_unavailable_metrics_not_zero_and_oos_status_not_silently_changed(self):
        value = copy.deepcopy(self.payload); value['portfolios']['original']['sharpe']=0
        with self.assertRaises(ValueError): validate_payload(value,self.folder)
        value = copy.deepcopy(self.payload); value['oos_status']='DONE'
        with self.assertRaises(ValueError): validate_payload(value,self.folder)

    def test_every_horizon_requires_its_own_uncertainty(self):
        for field in ('cc_iid_interval','theta_iid_interval'):
            value=copy.deepcopy(self.payload)
            value['studies']['corrected']['horizons'][0][field]=[None,None]
            with self.subTest(field=field),self.assertRaises(ValueError):validate_payload(value,self.folder)

    def test_missing_curve_values_preserved_and_future_data_refused(self):
        path = self.folder / 'curve.csv'
        path.write_text('date,nav\n2024-01-02,100\n2024-01-03,\n2024-01-04,101\n')
        rows = read_public_nav(path)
        self.assertNotEqual(rows[1][1],rows[1][1])
        path.write_text('date,nav\n2026-01-02,100\n')
        with self.assertRaises(ValueError): read_public_nav(path)

    def test_two_page_geometry_preflight_without_pdf(self):
        (self.folder / 'finalreport_payload.json').write_text(json.dumps(self.payload))
        report = make_pdf(self.folder,self.folder/'must_not_exist.pdf',preflight_only=True)
        self.assertEqual(report['pages'],2)
        self.assertTrue(all(height <= 684 for height in report['body_heights_points']))
        self.assertFalse((self.folder/'must_not_exist.pdf').exists())

    def test_causal_unavailable_metrics_remain_headline_and_fit_two_pages(self):
        self.payload['portfolios']['causal']=copy.deepcopy(self.payload['portfolios']['corrected'])
        self.payload['portfolio_headline']='causal'
        self.payload['portfolio_repair']={'event_evidence_version':'corrected_is_v2',
                                          'selection_basis':'OBJECTIVE_TIMING_REPAIR_NOT_PERFORMANCE'}
        (self.folder/'finalreport_payload.json').write_text(json.dumps(self.payload))
        report=make_pdf(self.folder,self.folder/'no.pdf',preflight_only=True)
        self.assertEqual(report['pages'],2)
        self.assertEqual(self.payload['portfolios']['causal']['status'],'UNAVAILABLE')
        self.payload['portfolio_headline']='corrected'
        with self.assertRaisesRegex(ValueError,'explicit current timing repair'):
            validate_payload(self.payload,self.folder)


if __name__=='__main__': unittest.main()
