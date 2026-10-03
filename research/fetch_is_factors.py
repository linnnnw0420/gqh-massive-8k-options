"""Plan or fetch the fixed IS market/value/momentum ETF proxy inputs."""
from __future__ import annotations
import json
import pandas as pd
from diagnostics_common import (argument_parser, load_snapshot, private_cache,
                                provenance, resolve_paths, sanitized_main, save_or_match_manifest)
from fetch_uniform_quotes import auth, fetch_one

TICKERS = ('SPY','IWD','IWF','MTUM')


def plan(paths):
    load_snapshot(paths)  # Enforce IS before any authentication or data request.
    items = [{'kind':'factor_bars','key':ticker,
              'path':f'/v2/aggs/ticker/{ticker}/range/1/day/2024-01-01/2025-12-31',
              'params':{'adjusted':'true','sort':'asc','limit':50000}} for ticker in TICKERS]
    manifest = {**provenance(paths), 'requests':items,
                'factors':['market_SPY','value_IWD_minus_IWF','momentum_MTUM_minus_SPY'],
                'units':'split-adjusted ETF price returns; excludes dividends; not Fama-French factors',
                'regression_start':'2024-01-03','regression_end':'2025-12-31','hac_lags':21,
                'portfolio_cash_rate':0,'return_selected_factors':False}
    return save_or_match_manifest(paths.work_dir / 'factor_proxy_manifest.json', manifest)


def main():
    paths = resolve_paths(argument_parser(__doc__).parse_args())
    manifest = plan(paths)
    if not paths.execute:
        print(json.dumps({'requests':len(manifest['requests']),'execute':False,'oos_access':False}))
        return
    cache = private_cache(paths, 'factor_proxy_is_v1')
    key = auth(paths.project); reports = []; prices = {}
    for item in manifest['requests']:
        record = fetch_one(item,key,cache)
        if record['status'] != 'OK':
            raise RuntimeError('Factor proxy input unavailable; no alternate ticker selected')
        rows = record.get('rows',[])
        table = pd.DataFrame(rows)
        dates = pd.to_datetime(table['t'],unit='ms',utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
        if not dates.between('2024-01-01','2025-12-31').all() or dates.duplicated().any():
            raise RuntimeError('Factor rows outside declared date/schema')
        prices[item['key']] = pd.Series(table['c'].to_numpy(),index=dates)
        reports.append({'ticker':item['key'],'status':record['status'],'rows':len(rows)})
    key = None
    returns = pd.DataFrame(prices).sort_index().pct_change(fill_method=None)
    factors = pd.DataFrame({'market_SPY':returns['SPY'],
                            'value_IWD_minus_IWF':returns['IWD']-returns['IWF'],
                            'momentum_MTUM_minus_SPY':returns['MTUM']-returns['SPY']})
    factors = factors.loc['2024-01-03':'2025-12-31']
    factors.to_csv(paths.work_dir / 'factor_proxy_inputs.private.csv',index_label='date')
    report = {'sources':reports,'factor_rows':len(factors),'missing_cells':int(factors.isna().sum().sum()),'oos_read':False}
    (paths.work_dir / 'factor_fetch_summary.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    sanitized_main(main)
