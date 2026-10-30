"""Conservative raw ETF quality gate. Does not repair or invent observations."""
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo


def inspect_etf(j, end_month='2026-09'):
    z=ZoneInfo(j['meta']['exchangeTimezoneName'])
    day=lambda t:datetime.fromtimestamp(t,z).date().isoformat()
    times=j['timestamp'];close=j['indicators']['quote'][0]['close'];adj=j['indicators']['adjclose'][0]['adjclose']
    if not(len(times)==len(close)==len(adj)):
        raise ValueError('timestamp/close/adjusted length mismatch')
    dividends={day(d['date']):float(d['amount']) for d in j.get('events',{}).get('dividends',{}).values()}
    last_reported={};last_valid={};issues=[];previous=None;gap=[]
    for t,c,a in zip(times,close,adj):
        d=day(t)
        if d[:7]>end_month:continue
        last_reported[d[:7]]=d
        if c is None or a is None:
            gap.append(d);continue
        if not(math.isfinite(c) and math.isfinite(a) and c>0 and a>0):
            raise ValueError('invalid ETF price')
        last_valid[d[:7]]=d;factor=a/c
        if previous:
            # Missing quote on an ex-date prevents exact prior-close validation.
            pending=[x for x in gap if dividends.get(x,0)!=0]
            distribution=dividends.get(d,0)
            actual=factor/previous[2]
            if pending:
                issues.append({'kind':'dividend_on_missing_quote','dates':pending,'next_valid':d})
            elif distribution and gap:
                issues.append({'kind':'dividend_prior_quote_gap','date':d,'amount':distribution,'actual_factor_change':actual-1,'missing_dates':gap[:]})
            else:
                expected=1/(1-distribution/previous[1])
                if abs(actual-expected)>5e-5:
                    issues.append({'kind':'adjustment_factor_mismatch','date':d,'difference':actual-expected})
        previous=(d,c,factor);gap=[]
    for m,last in last_reported.items():
        if last_valid.get(m)!=last:
            issues.append({'kind':'missing_last_reported_month_quote','month':m,'last_reported':last,'last_valid':last_valid.get(m)})
    return {'status':'BLOCKED_SOURCE_RECONCILIATION' if issues else 'INTERNAL_CHECK_PASS',
            'issues':issues,'limitation':'reported-date validation is not an exchange calendar or independent source certification'}


def enforce(root):
    checks={}
    for symbol in ('SPY','IEF','069500.KS','148070.KS'):
        payload=json.loads((root/'raw/yahoo'/f'{symbol}.json').read_text())['chart']['result'][0]
        checks[symbol]=inspect_etf(payload)
    bad=[s for s,r in checks.items() if r['status']!='INTERNAL_CHECK_PASS']
    if bad:
        raise ValueError('BLOCKED_SOURCE_RECONCILIATION: '+','.join(bad))
    return checks
