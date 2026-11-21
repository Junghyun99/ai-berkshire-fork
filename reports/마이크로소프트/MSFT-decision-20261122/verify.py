"""판단 사례의 전사값 대조·산술 재현. 원천 인증/투자 판정기는 아니다."""
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: python verify.py /path/to/tools/financial_rigor.py')
    rigor = Path(sys.argv[1]).resolve()
    evidence = json.loads((HERE / 'evidence.json').read_text())
    log = []
    for row in evidence['observations']:
        cmd = [sys.executable, str(rigor), 'cross-validate', '--field', row['id'], '--values', json.dumps({'Microsoft': row['primary'], 'StockAnalysis': row['secondary']}), '--unit', 'USD million', '--tolerance', '0.01']
        result = subprocess.run(cmd, capture_output=True, text=True)
        log.append({'command': cmd[2:], 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode or row['primary'] != row['secondary']:
            raise SystemExit('Source pair mismatch: ' + row['id'])
    v = {row['id']: Decimal(str(row['primary'])) for row in evidence['observations']}
    current = v['ocf_2026Q3'] - v['cash_ppe_2026Q3']
    prior = v['ocf_2025Q3'] - v['cash_ppe_2025Q3']
    calculations = {'fcf_current_usd_million': str(current), 'fcf_prior_usd_million': str(prior), 'fcf_yoy_pct': str((current / prior - 1) * 100), 'cash_ppe_to_ocf_current_pct': str(v['cash_ppe_2026Q3']/v['ocf_2026Q3']*100), 'cash_ppe_to_ocf_prior_pct': str(v['cash_ppe_2025Q3']/v['ocf_2025Q3']*100)}
    for expr in ['58000-39367', '45057-19394', '((58000-39367)/(45057-19394)-1)*100']:
        r = subprocess.run([sys.executable, str(rigor), 'calc', '--expr', expr], capture_output=True, text=True)
        log.append({'command':['calc','--expr',expr],'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode:
            raise SystemExit('Calculation failure')
    out = {'scope':'8 source pairs and 3 arithmetic commands; no strategy or policy tests', 'calculations':calculations,'commands':log}
    (HERE / 'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pairs':len(evidence['observations']),'calculations':calculations},ensure_ascii=False))

if __name__ == '__main__':
    main()
