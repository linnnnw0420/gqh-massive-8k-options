"""Plan or execute the predeclared IS-only quote/metadata diagnostic scope."""
from __future__ import annotations
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from diagnostics_common import (argument_parser, load_snapshot, private_cache,
                                provenance, resolve_paths, sanitized_main,
                                save_or_match_manifest, sha256)
from quote_valuation import build_scope

SAFE_FIELDS = {'sip_timestamp','sequence_number','bid_price','ask_price','bid_size','ask_size','bid_exchange','ask_exchange','conditions'}


def auth(project):
    key = os.environ.get('MASSIVE_API_KEY','').strip()
    if key:
        return key
    for line in (project / '.env').read_text().splitlines():
        name, sep, value = line.partition('=')
        if sep and name.strip() == 'MASSIVE_API_KEY':
            return value.strip().strip('"').strip("'")
    raise RuntimeError('Authentication unavailable')


def plan(paths):
    scopes = build_scope(load_snapshot(paths))
    req = {}
    for row in scopes:
        key = row['contract']+'|'+row['day']
        req['quote|'+key] = {'kind':'quote','key':key,'path':'/v3/quotes/'+row['contract'],
                            'params':{'timestamp.gte':row['start_ns'],'timestamp.lt':row['cutoff_ns'],
                                      'order':'desc','sort':'timestamp','limit':64}}
        if row['is_entry'] or row['is_scope_end']:
            req['metadata|'+key] = {'kind':'metadata','key':key,'path':'/v3/reference/options/contracts/'+row['contract'],
                                   'params':{'as_of':row['day']}}
    for ticker in sorted({r['ticker'] for r in scopes}):
        dates = [r['day'] for r in scopes if r['ticker']==ticker]
        lo, hi = min(dates), max(dates)
        req['splits|'+ticker] = {'kind':'splits','key':ticker,'path':'/v3/reference/splits',
                                'params':{'ticker':ticker,'execution_date.gte':lo,'execution_date.lte':hi,'limit':1000}}
        req['dividends|'+ticker] = {'kind':'dividends','key':ticker,'path':'/v3/reference/dividends',
                                   'params':{'ticker':ticker,'ex_dividend_date.gte':lo,'ex_dividend_date.lte':hi,'limit':1000}}
    manifest = {**provenance(paths), 'version':'uniform-fixed-ledger-v1',
                'quote_rows':len(scopes),'requests':list(req.values()),
                'primary_age_seconds':60,'age_sensitivity_seconds':300,'max_leg_time_span_seconds':60,
                'max_attempts_per_request':3,'workers':4}
    return save_or_match_manifest(paths.work_dir / 'uniform_quote_manifest.json', manifest)


def fetch_one(item, key, cache):
    # Same request identity, response selection and retry conventions as the
    # declared original helper. Immutable cached responses are reused by exact
    # full-request hash in the private shared sponsor-data cache.
    identity = hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
    dest = cache / (identity+'.json')
    if dest.exists():
        prior = json.loads(dest.read_text())
        if (prior.get('request_hash') != identity or prior.get('kind') != item['kind']
                or prior.get('key') != item['key']):
            raise ValueError('Cached response identity does not match the canonical request.')
        return prior
    record = {'kind':item['kind'],'key':item['key'],'request_hash':identity,'status':'UNAVAILABLE','attempts':0}
    for attempt in range(3):
        record['attempts'] += 1
        try:
            response = requests.get('https://api.massive.com'+item['path'],params=item['params'],
                                    headers={'Authorization':'Bearer '+key},timeout=(10,30),allow_redirects=False)
            record['http_status'] = response.status_code
            if response.status_code in (429,500,502,503,504) and attempt<2:
                response.close(); time.sleep(2**attempt); continue
            if response.status_code != 200:
                record['status'] = 'HTTP_'+str(response.status_code); response.close(); break
            payload = response.json(); response.close()
            if not isinstance(payload,dict) or payload.get('status') not in ('OK','DELAYED'):
                record['status'] = 'API_ERROR_OR_UNEXPECTED_STATUS'; break
            values = payload.get('results',[])
            if item['kind'] == 'quote':
                if not isinstance(values,list) or any(not isinstance(r,dict) for r in values):
                    record['status'] = 'INVALID_QUOTE_RESULTS'; break
                record['rows'] = [{k:v for k,v in r.items() if k in SAFE_FIELDS} for r in values if isinstance(r,dict)]
                record['has_more_older_records'] = bool(payload.get('next_url'))
            elif item['kind'] == 'metadata':
                record['result'] = values if isinstance(values,dict) else None
            else:
                if not isinstance(values,list) or any(not isinstance(r,dict) for r in values):
                    record['status'] = 'INVALID_LIST_RESULTS'; break
                record['rows'] = values
                if payload.get('next_url'):
                    record['status'] = 'INCOMPLETE_ACTION_COVERAGE'; break
            record['status'] = 'OK'; break
        except Exception:
            record['status'] = 'SANITIZED_REQUEST_ERROR'
            if attempt<2:
                time.sleep(2**attempt)
    dest.write_text(json.dumps(record,allow_nan=False), encoding='utf-8')
    return record


def main():
    paths = resolve_paths(argument_parser(__doc__).parse_args())
    manifest = plan(paths)
    counts = {k:sum(r['kind']==k for r in manifest['requests']) for k in ('quote','metadata','splits','dividends')}
    print(json.dumps({'scope':counts,'total':len(manifest['requests']),'execute':paths.execute}),flush=True)
    if not paths.execute:
        return
    cache = private_cache(paths, 'uniform_fixed_ledger_v1')
    key = auth(paths.project); records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_one,item,key,cache) for item in manifest['requests']]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records)%100 == 0:
                print(json.dumps({'completed':len(records),'of':len(futures)}),flush=True)
    key = None
    quotes = {r['key']:r for r in records if r['kind']=='quote'}
    metadata = {r['key']:r.get('result') for r in records if r['kind']=='metadata'}
    actions = [r for r in records if r['kind'] in ('splits','dividends')]
    output = {'quotes':quotes,'metadata':metadata,'actions':actions,
              'manifest_hash':sha256(paths.work_dir / 'uniform_quote_manifest.json')}
    (paths.work_dir / 'uniform_quote_inputs.private.json').write_text(json.dumps(output,allow_nan=False), encoding='utf-8')
    from collections import Counter
    report = {'requests':len(records),'statuses':dict(Counter(r['status'] for r in records)),
              'metadata_standard_multiplier':sum(r.get('result',{}).get('shares_per_contract')==100 for r in records if r['kind']=='metadata' and isinstance(r.get('result'),dict)),
              'action_record_counts':[{'kind':r['kind'],'ticker':r['key'],'status':r['status'],'count':len(r.get('rows',[]))} for r in actions]}
    (paths.work_dir / 'uniform_quote_fetch_summary.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    sanitized_main(main)
