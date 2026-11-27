"""고정 보고서 연결 및 합성 비중 산술 확인. 백테스트/투자 승인 아님."""
import hashlib
import json
import sys
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import decision_ledger as dl
import position_plan as pp

FILES = [
    'reports/어도비/최종보고서.md',
    'reports/어도비/06-리스크토론-비중.md',
    'reports/saa/20261120-equity-matched/README.md',
    'reports/saa/20261120-equity-matched/results.json',
    'reports/policies/ai-berkshire-primary/draft-v0.4-2026-10-28.md',
    'tools/decision_ledger.py', 'tools/position_plan.py',
]
report = (ROOT / FILES[0]).read_text()
label = dl.parse_label(report)
plan = pp.parse_plan(report)
assert label['판단'] == '매수' and plan['비중상한'] == 5
assert plan == pp.parse_plan((ROOT / FILES[1]).read_text())
saa = json.loads((ROOT / FILES[3]).read_text())
assert saa['quality'] == 'research_proxy'
assert saa['variants']['baseline']['oos_end'] == '2026-09'
assert dl.parse_run_info(report)['작성일'] == '2026-11-02'
assert 'DRAFT' in (ROOT / FILES[4]).read_text()
# 원 SAA 문서의 동일가중 5자산 기준선. 아래 x는 합성 산술 예시일 뿐 제안값이 아니다.
examples = []
for x in [D('0'), D('0.02'), D('0.2')]:
    weights = {'KR_EQUITY': D('.2'), 'US_SP500': D('.2')-x,
               'US_NASDAQ100': D('.2'), 'KR_TREASURY10Y': D('.2'),
               'US_TREASURY7_10Y': D('.2'), 'ADBE': x}
    assert sum(weights.values()) == 1
    assert all(v >= 0 for v in weights.values())
    assert sum(weights[k] for k in ['KR_EQUITY','US_SP500','US_NASDAQ100','ADBE']) == D('.6')
    examples.append({'synthetic_x': str(x), 'weights': {k:str(v) for k,v in weights.items()}})
print(json.dumps({'kind':'input_contract_and_synthetic_arithmetic_only',
    'source_commit':'c6f0fa147bf649e133aa0895fd976665eb9b67c2',
    'original_opinion':label['판단'], 'original_cap_percent':plan['비중상한'],
    'target_weight':None, 'weight_denominator':None,
    'historical_oos_end':'2026-09','opinion_written':'2026-11-02',
    'historical_insertion_allowed':False, 'policy_status':'DRAFT',
    'synthetic_examples':examples,
    'sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}},ensure_ascii=False,indent=2))
