"""Immutable primary valuation policy. No I/O and no missing-price repair by invention."""
from types import MappingProxyType
import hashlib
import json

POLICY = MappingProxyType({
    'version': 'FIXED_LAST_TRADE_MISSINGNESS_V1',
    'mark_source': 'ORIGINAL_DAILY_OPTION_AGGREGATES',
    'max_stale_sessions': 3,
    'synthetic_stock': 'CALL_PUT_PARITY_FLAT_4_PERCENT_NO_DIVIDEND',
    'cost_haircut_each_leg_each_side': .05,
    'fallback_to_quotes': False,
    'fill_missing_nav': False,
    'bridge_missing_return': False,
    'unknown_entry_cash': 'PERMANENT_UNKNOWN_COMMITTED_FILL',
    'missing_fixed_exit': 'UNRESOLVED_NO_LATER_EXIT_SUBSTITUTION',
    'unknown_prior_book': 'PAUSE_NEW_ORDERS_KEEP_FIXED_EXITS',
    'window_end': 'MARK_IN_WINDOW_KEEP_OPEN_NO_FORCED_LIQUIDATION',
    'full_path_risk_if_incomplete': 'UNAVAILABLE_WITH_COVERAGE_COUNTS',
    'quote_diagnostics': 'SEPARATE_CONDITIONAL_EVIDENCE_NEVER_PRIMARY_FALLBACK',
})


def policy_sha256():
    return hashlib.sha256(json.dumps(dict(POLICY), sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def assert_primary_valuation(namespace):
    for name, expected in {'MAX_STALE_SESSIONS': 3, 'RISK_FREE': .04, 'COST_HAIRCUT': .05}.items():
        if namespace.get(name) != expected:
            raise ValueError('Frozen valuation configuration differs: '+name)
