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
# 합성 산술 예시. e는 총자산 중 주식 비중, s는 주식 안에서의 종목 비중이다.
examples = []
for equity, stocks, theme in [
    (D('.6'), [D('.6'), D('.4')], D('0')),
    (D('.4'), [D('.5'), D('.3')], D('.2')),
]:
    assert sum(stocks) + theme == 1
    portions = [equity * share for share in stocks]
    theme_weight = equity * theme
    assert sum(portions) + theme_weight == equity
    assert sum(portions) + theme_weight + (1 - equity) == 1
    examples.append(dict(equity=str(equity), stock_weights=list(map(str, portions)),
                         theme_weight=str(theme_weight), other_assets=str(1 - equity)))

print(json.dumps(dict(input_commit='c6f0fa147bf649e133aa0895fd976665eb9b67c2',
    original_opinion=label['판단'], reported_cap_percent=plan['비중상한'],
    equity_target=None, adobe_target=None, policy_status='DRAFT',
    synthetic_examples=examples,
    sha256={f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}),
    ensure_ascii=False, indent=2))
