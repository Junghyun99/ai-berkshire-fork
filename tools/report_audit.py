#!/usr/bin/env python3
"""Report Audit Tool for AI Berkshire.

데이터 샘플링 도구: 연구 보고서에서 추출15%신뢰할 수 있는 소스와 비교한 재무 데이터 포인트，
통과하면 갈 수 있습니다. 실패하면 거절되고 그 이유가 설명됩니다.。

Zero external dependencies — uses only Python stdlib.
Requires Python >= 3.7.

워크플로(3단계）：
  Step 1 — 발췌데이터 포인트, 무작위 15% 샘플링：
    python3 tools/report_audit.py extract --report reports/xxx.md

  Step 2 — Claude 샘플링 목록의 각 데이터 포인트에 대해 신뢰할 수 있는 소스에서 가져옵니다.（macrotrends/
            stockanalysis/aastocks/eastmoney）번호를 받아 입력하세요. fetched_value

  Step 3 — 검증 결과를 입력하면 정확하게 출력됩니다./평결을 반환：
    python3 tools/report_audit.py verdict --results '[...]'

  한 단계로 완료(추출만 가능)+네트워크 검증 없이 무작위 검사 목록 인쇄）：
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run
"""

import argparse
import json
import math
import os
import re
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN
from random import Random

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)

# ---------------------------------------------------------------------------
# 데이터 포인트 추출: from Markdown 보고서에서 재무 수치 식별
# ---------------------------------------------------------------------------

# 일치 패턴: 숫자 + 단위(앞에 상황별 라벨이 붙음)
# 예: 소득：1,23910억、PE 18.8x、매출총이익률 56%、시장가치 ~$5,6701억
_PATTERNS = [
    # 백분율
    (r'([\d,，\.]+)\s*%',                        '%',    'percent'),
    # 10억/10억 달러/10억 홍콩달러
    (r'([\d,，\.]+)\s*1억(원|달러|홍콩 달러|RMB|USD|HKD)?', '1억',    'hundred_million'),
    # 다수의 PE/PB/PS
    (r'([\d,，\.]+)\s*[xX타임스]',                   'x',    'multiple'),
    # 수조
    (r'([\d,，\.]+)\s*수조',                      '수조', 'trillion'),
    # 달러 절대 가치（B/T）
    (r'\$\s*([\d,，\.]+)\s*([BMT1억])',             '$',    'usd_abs'),
    # 순수 정수(예: 시가총액, 수익, 사용자 수 등)가 테이블에 표시됩니다. | 내부에）
    (r'\|\s*[~~에 대한]?\$?([\d,，\.]+)\s*\|',          '',     'table_num'),
]

_LABEL_RE = re.compile(
    r'(?P<label>[^\|\n：:]{2,25})[：:\s]+[~~에 대한]?\$?(?P<num>[\d,，\.]+)\s*(?P<unit>1억[홍콩 위안메이]?원?|수조|[xX타임스]|%|[BMT])?'
)

_TABLE_ROW_RE = re.compile(
    r'\|\s*(?P<label>[^|]{1,40})\s*\|\s*[~~에 대한]?\$?(?P<num>[\d,，\.]+)\s*(?P<unit>1억[홍콩 위안메이]?원?|수조|[xX타임스]|%|[BMT])?\s*\|'
)


def _clean_num(s: str) -> float:
    """쉼표와 중국어 쉼표가 있는 숫자 문자열을 다음으로 변환합니다. float。"""
    s = s.replace(',', '').replace('，', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def _is_valid_label(label: str) -> bool:
    """레이블이 의미 있는 금융 분야 이름인지 확인하고 노이즈를 필터링합니다.。"""
    label = label.strip()
    # 너무 짧다
    if len(label) < 2:
        return False
    # 순수한 숫자 또는 순수한 연도
    if re.fullmatch(r'[\d\s연도 분기Q]+', label):
        return False
    # 기호가 있는/markdown시작 표시
    if re.match(r'^[+\-\*#\|~\$>_`]', label):
        return False
    # 포함하다 markdown 용감한/코드 마크업
    if '**' in label or '`' in label or '__' in label:
        return False
    # 순수 성장 기호가 포함된 라벨(예: +56%、-13% 별도의 라벨）
    if re.fullmatch(r'[+\-]?\d+(\.\d+)?%', label):
        return False
    # 일반적인 의미 없는 태그
    _SKIP = {'원천', 'sources', 'source', '설명하다', '알아채다', '주목', '데이터 소스',
             'n/a', '—', '-', '/', '총', 'total', '단위', '경향'}
    if label.lower() in _SKIP:
        return False
    return True


# 2열 테이블 행：| 상표 | 수치 unit |（재무 보고용으로 설계됨 KV 테이블 디자인）
_KV_TABLE_RE = re.compile(
    r'^\|\s*(?P<label>[^|*\n]{2,40}?)\s*\|\s*[~~에 대한]?\$?(?P<num>[\d,，\.]+)\s*'
    r'(?P<unit>1억[홍콩 위안메이]?원?|수조|[xX타임스]|%|[BMT1억])?\s*[\|（\(]'
)

# 태그됨 KV 행: 라벨: 값 단위
_KV_LABEL_RE = re.compile(
    r'(?P<label>[\u4e00-\u9fa5A-Za-z][^\|\n：:*]{1,30})[：:]\s*[~~에 대한]?\$?'
    r'(?P<num>[\d,，\.]+)\s*(?P<unit>1억[홍콩 위안메이]?원?|수조|[xX타임스]|%|[BMT])?'
)


def _parse_md_tables(lines: list) -> list:
    """분석하다 Markdown 모든 테이블 입력, 반환 (row_label, col_header, value, unit, lineno, raw) 목록。"""
    results = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 헤더 행 감지(포함 | 별도의 줄이 아닌）
        if '|' in line and not re.match(r'^\|[\-\s\|:]+\|$', line):
            headers_raw = [h.strip().strip('*_').strip() for h in line.split('|')]
            headers_raw = [h for h in headers_raw if h]
            # 다음 줄은 구분자 줄이어야 합니다.
            if i + 1 < len(lines) and re.match(r'^\|[\-\s\|:]+\|$', lines[i+1].strip()):
                i += 2  # 구분선 건너뛰기
                # 데이터 행 읽기
                while i < len(lines):
                    dline = lines[i].strip()
                    if not dline or not dline.startswith('|'):
                        break
                    cells = [c.strip().strip('*_~').strip() for c in dline.split('|')]
                    cells = [c for c in cells if c != '']
                    if len(cells) < 2:
                        i += 1
                        continue
                    row_label = cells[0]
                    for col_idx, cell in enumerate(cells[1:], start=1):
                        col_header = headers_raw[col_idx] if col_idx < len(headers_raw) else f'목록{col_idx}'
                        # 발췌 cell 숫자+단위
                        m = re.search(
                            r'[~~에 대한]?\$?([\d,，\.]+)\s*(1억[홍콩 위안메이]?원?|수조|[xX타임스]|%|[BMT])?',
                            cell
                        )
                        if m:
                            val = _clean_num(m.group(1))
                            unit = (m.group(2) or '').strip()
                            if val and val != 0 and val < 1e15:
                                results.append((row_label, col_header, val, unit, i + 1, dline))
                    i += 1
                continue
        i += 1
    return results


def extract_data_points(md_text: str) -> list:
    """~에서 Markdown 보고서에서 식별 가능한 모든 재무 데이터 포인트를 추출합니다.。

    세 가지 유형의 구조를 다루고 있습니다.：
      1. 여러 열 Markdown 테이블(기본 소스）：(행 라벨 + 열 헤더) → 수치
      2. 콜론과 함께 KV 행: 라벨: 값 단위
      3. 굵은 숫자선：**수치** 단위

    반품 list of dict：
      {id, label, reported_value, unit, raw_text, line_number}
    """
    points = []
    seen = set()

    def _add(label, val, unit, lineno, raw):
        label = re.sub(r'[\*_`]+', '', label).strip()
        if not _is_valid_label(label):
            return
        if val is None or val == 0 or val > 1e15:
            return
        # 순수한 연도 필터링/4분의 1
        if re.fullmatch(r'(20\d{2}|Q[1-4]|\d{4}\s*Q[1-4])', label.strip()):
            return
        key = f"{label}|{round(val,4)}|{unit}"
        if key in seen:
            return
        seen.add(key)
        points.append({
            'id': len(points) + 1,
            'label': label,
            'reported_value': val,
            'unit': unit,
            'raw_text': raw[:120],
            'line_number': lineno,
        })

    lines = md_text.split('\n')
    in_code = False

    # --- 1. 다중 열 테이블 ---
    for row_label, col_header, val, unit, lineno, raw in _parse_md_tables(lines):
        # 의미 없는 라인 라벨 건너뛰기
        if not _is_valid_label(row_label):
            continue
        # 의미 없는 열 헤더 건너뛰기（YoY성장률 항목은 별도로 표시되며, 검증자료로 사용되지 않습니다.）
        if col_header.upper() in ('YOY', 'YOY성장률', '성장률', '전년 대비', '변화', '경향', '설명하다', '주목'):
            continue
        # label = "행 라벨 · 열 헤더"（열 머리글이 행 레이블에 추가되는 경우）
        if col_header and col_header != row_label:
            label = f"{row_label} · {col_header}"
        else:
            label = row_label
        _add(label, val, unit, lineno, raw)

    # --- 2. KV 결장선 ---
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if in_code or stripped.startswith('> ') or re.match(r'^#{1,6}\s', stripped):
            continue
        if '|' in stripped:
            continue  # 양식이 위에서 처리되었습니다.

        for m in _KV_LABEL_RE.finditer(stripped):
            label = m.group('label')
            val = _clean_num(m.group('num'))
            unit = (m.group('unit') or '').strip()
            _add(label, val, unit, lineno, stripped)

    return points


def sample_points(points: list, ratio: float = 0.15, seed: int = None) -> list:
    """무작위로 선택됨 ratio 데이터 포인트 비율, 최소 3 숫자는 기껏해야 30 개인。"""
    n = max(3, min(30, math.ceil(len(points) * ratio)))
    n = min(n, len(points))
    rng = Random(seed)
    sampled = rng.sample(points, n)
    # 수동 비교를 용이하게 하기 위해 줄 번호별로 정렬
    return sorted(sampled, key=lambda p: p['line_number'])


# ---------------------------------------------------------------------------
# 정확한/평결을 반환
# ---------------------------------------------------------------------------

_TOLERANCE = 0.01   # 1% 용인


def _pct_diff(reported: float, fetched: float) -> float:
    """상대편차 (absolute)。"""
    if reported == 0:
        return 0.0 if fetched == 0 else float('inf')
    return abs(reported - fetched) / abs(reported)


def render_verdict(results: list, report_name: str = "") -> dict:
    """
    검증 결과에 따라 출력이 정확합니다./평결을 반환。

    results: list of dict，각 항목에는 다음이 포함됩니다.：
      - id, label, reported_value, unit, fetched_value, fetched_source
      - (선택 과목) fetched_value2, fetched_source2   ← 보조 소스

    반품：
      {
        'verdict': 'PASS' | 'FAIL',
        'pass_count': int,
        'fail_count': int,
        'total': int,
        'fail_items': [...],
        'summary': str,
      }
    """
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

    print('=' * 70)
    print(f'{BOLD}보고서 데이터 샘플링 — 정확한/평결을 반환{RESET}')
    if report_name:
        print(f'보고서：{report_name}')
    print('=' * 70)
    print()

    fail_items = []
    warn_items = []

    for item in results:
        label = item.get('label', '?')
        reported = float(item.get('reported_value', 0))
        unit = item.get('unit', '')
        fetched = item.get('fetched_value')
        source = item.get('fetched_source', '?')
        fetched2 = item.get('fetched_value2')
        source2 = item.get('fetched_source2', '')

        # --- 기본 소스 비교 ---
        if fetched is None:
            # 제공된 확인 값이 없습니다. → 건너뛰기(합격에 포함되지 않음)/실패하다）
            print(f'  ⬜ [{item["id"]:>2}] {label[:35]:35s} {reported:>12.2f} {unit}  →  [확인 값이 제공되지 않았습니다. 건너뛰세요.]')
            continue

        fetched = float(fetched)
        diff1 = _pct_diff(reported, fetched)

        # --- 보조 소스 비교(있는 경우）---
        diff2 = None
        if fetched2 is not None:
            fetched2 = float(fetched2)
            diff2 = _pct_diff(reported, fetched2)

        # 판사
        pass1 = diff1 <= _TOLERANCE
        pass2 = (diff2 is None) or (diff2 <= _TOLERANCE)

        if pass1 and pass2:
            status = f'{GREEN}✅ 통과하다{RESET}'
            detail = f'{source}: {fetched:.2f} (편차 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (편차 {diff2*100:.2f}%)'
        elif not pass1 and not pass2:
            status = f'{RED}❌ 실패한{RESET}'
            detail = f'{source}: {fetched:.2f} (편차 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (편차 {diff2*100:.2f}%)'
            fail_items.append({
                'id': item['id'],
                'label': label,
                'reported': reported,
                'unit': unit,
                'fetched': fetched,
                'source': source,
                'fetched2': fetched2,
                'source2': source2,
                'diff1_pct': round(diff1 * 100, 2),
                'diff2_pct': round(diff2 * 100, 2) if diff2 is not None else None,
                'raw_text': item.get('raw_text', ''),
                'line_number': item.get('line_number', 0),
            })
        else:
            # 한 소스는 통과하고 다른 소스는 통과하지 못함 → 경고하다, 실패로 간주하지 않음
            status = f'{YELLOW}⚠️  경고하다{RESET}'
            detail = f'{source}: {fetched:.2f} (편차 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (편차 {diff2*100:.2f}%)'
            warn_items.append({
                'id': item['id'], 'label': label,
                'reported': reported, 'unit': unit,
                'diff1_pct': round(diff1 * 100, 2),
                'diff2_pct': round(diff2 * 100, 2) if diff2 is not None else None,
            })

        print(f'  {status} [{item["id"]:>2}] {label[:35]:35s}  보고서: {reported:>12.2f} {unit}')
        print(f'              {" " * 38}{detail}')

    print()
    print('-' * 70)

    total = len([r for r in results if r.get('fetched_value') is not None])
    fail_count = len(fail_items)
    warn_count = len(warn_items)
    pass_count = total - fail_count - warn_count

    print(f'  총 무작위 검사 횟수: {total}  |  통과하다: {GREEN}{pass_count}{RESET}  |  경고하다: {YELLOW}{warn_count}{RESET}  |  실패한: {RED}{fail_count}{RESET}')
    print()

    if fail_count == 0:
        print(f'{BOLD}{GREEN}【가결] 무작위 검사자료 전량 통과 및 보고서 공개 가능。{RESET}')
        verdict = 'PASS'
    else:
        print(f'{BOLD}{RED}【반격하다】{fail_count} 데이터 포인트가 검증을 통과하지 못한 경우 보고서를 수정하고 재검토해야 합니다.。{RESET}')
        print()
        print(f'{BOLD}다시 전화한 이유：{RESET}')
        for fi in fail_items:
            print(f'  ❌ 아니요. {fi["line_number"]} 좋아요 | {fi["label"]}')
            print(f'     보고서 값：{fi["reported"]} {fi["unit"]}')
            print(f'     {fi["source"]}：{fi["fetched"]}  （편차 {fi["diff1_pct"]}%）')
            if fi.get('fetched2') is not None:
                print(f'     {fi["source2"]}：{fi["fetched2"]}  （편차 {fi["diff2_pct"]}%）')
            print(f'     원래의：{fi["raw_text"][:80]}')
            print()
        verdict = 'FAIL'

    if warn_count > 0:
        print(f'{YELLOW}알아채다：{warn_count} 두 소스 간에 데이터 포인트가 일치하지 않습니다(1%），어쩌면 구경의 차이일 수도 있겠네요（GAAP/Non-GAAP또는 환율), 수동으로 검토하시기 바랍니다。{RESET}')
        for wi in warn_items:
            print(f'  ⚠️  {wi["label"]}  보고서:{wi["reported"]} {wi["unit"]}  편차: {wi["diff1_pct"]}% / {wi["diff2_pct"]}%')

    print('=' * 70)

    return {
        'verdict': verdict,
        'pass_count': pass_count,
        'warn_count': warn_count,
        'fail_count': fail_count,
        'total': total,
        'fail_items': fail_items,
        'warn_items': warn_items,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Report Audit Tool — 연구 보고서 데이터 샘플링 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
작업흐름：

  Step 1 — 데이터 포인트 추출 및 무작위 샘플링 15%，출력 샘플링 목록：
    python3 tools/report_audit.py extract --report reports/텐센트/텐센트-research-20260408.md

  Step 2 — Claude 목록의 각 데이터 포인트에 대해 신뢰할 수 있는 소스에서 숫자를 얻습니다.，
            채우다 fetched_value / fetched_source / fetched_value2 / fetched_source2

  Step 3 — 검증 결과를 입력하면 정확하게 출력됩니다./평결을 반환：
    python3 tools/report_audit.py verdict --results '[
      {"id":1,"label":"영업이익","reported_value":7518,"unit":"1억","fetched_value":7518,"fetched_source":"macrotrends","fetched_value2":7500,"fetched_source2":"stockanalysis"},
      ...
    ]'

  1단계 미리보기(무작위 검사 목록만 인쇄, 검증 없음)）：
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run

  샘플링 비율 지정(기본값0.15）：
    python3 tools/report_audit.py extract --report reports/xxx.md --ratio 0.20

  고정된 무작위 시드(동일한 샘플 배치를 재현하기 위해)）：
    python3 tools/report_audit.py extract --report reports/xxx.md --seed 42
        """)

    sub = parser.add_subparsers(dest='command')

    # extract
    ext = sub.add_parser('extract', help='보고서에서 데이터 포인트를 추출하고 무작위로 샘플링합니다.')
    ext.add_argument('--report', required=True, help='보고서 파일 경로（Markdown）')
    ext.add_argument('--ratio', type=float, default=0.15, help='샘플링 비율, 기본값 0.15')
    ext.add_argument('--seed', type=int, default=None, help='무작위 시드(선택사항, 재생산용)）')
    ext.add_argument('--dry-run', action='store_true', help='인쇄만 되고 출력은 안됨 JSON')

    # verdict
    vrd = sub.add_parser('verdict', help='검증 결과에 따라 출력이 정확합니다./평결을 반환')
    vrd.add_argument('--results', required=True, help='JSON 다음을 포함한 배열 fetched_value 등 분야')
    vrd.add_argument('--report', default='', help='보고서 이름(선택 사항, 표시하는 데 사용됨)）')
    vrd.add_argument('--output-json', action='store_true', help='판결은 다음과 같습니다 JSON 출력 대상 stdout')

    args = parser.parse_args()

    if args.command == 'extract':
        if not os.path.exists(args.report):
            print(f'❌ 파일이 존재하지 않습니다: {args.report}', file=sys.stderr)
            sys.exit(1)

        with open(args.report, 'r', encoding='utf-8') as f:
            text = f.read()

        all_points = extract_data_points(text)
        sampled = sample_points(all_points, ratio=args.ratio, seed=args.seed)

        print('=' * 70)
        print(f'보고서 데이터 샘플링 체크리스트')
        print(f'문서：{args.report}')
        print(f'추출된 총 데이터 포인트：{len(all_points)}  |  샘플링 비율：{args.ratio:.0%}  |  무작위 검사 수량：{len(sampled)}')
        if args.seed is not None:
            print(f'무작위 시드：{args.seed}（동일한 배치의 샘플을 재현하는 데 사용할 수 있습니다.）')
        print('=' * 70)
        print()
        print(f'{"ID":>3}  {"줄 번호":>5}  {"데이터 라벨":<35}  {"보고서 값":>12}  {"단위"}')
        print(f'{"─"*3}  {"─"*5}  {"─"*35}  {"─"*12}  {"─"*6}')
        for p in sampled:
            print(f'{p["id"]:>3}  {p["line_number"]:>5}  {p["label"][:35]:<35}  {p["reported_value"]:>12.2f}  {p["unit"]}')
        print()
        print('↑ 위의 각 데이터 포인트에 대해 다음 소스에서 번호를 가져와 입력하세요. fetched_value：')
        print('  미국 주식：macrotrends.net（주인）+ stockanalysis.com（바이스）')
        print('  홍콩 주식：aastocks.com（주인）+ macrotrends ADR（바이스）')
        print('  A공유하다： eastmoney.com（주인）+ cninfo.com.cn（바이스）')
        print()

        if not args.dry_run:
            # 출력을 채울 수 있음 JSON 주형
            template = []
            for p in sampled:
                template.append({
                    'id': p['id'],
                    'label': p['label'],
                    'reported_value': p['reported_value'],
                    'unit': p['unit'],
                    'line_number': p['line_number'],
                    'raw_text': p['raw_text'],
                    'fetched_value': None,       # ← 주요 소스 검증 값을 입력하세요.
                    'fetched_source': '',        # ← 주요 소스 이름을 입력하세요.
                    'fetched_value2': None,      # ← 보조 소스 확인 값을 입력합니다(선택 사항).）
                    'fetched_source2': '',       # ← 보조 소스의 이름을 입력합니다(선택 사항).）
                })
            print('무작위 검사 목록 JSON（채우다 fetched_value 그 후에는 다음으로 전달하십시오. verdict 주문하다）：')
            print()
            print(json.dumps(template, ensure_ascii=False, indent=2))

    elif args.command == 'verdict':
        try:
            results = json.loads(args.results)
        except json.JSONDecodeError as e:
            print(f'❌ JSON 구문 분석 실패: {e}', file=sys.stderr)
            sys.exit(1)

        report_name = args.report or ''
        outcome = render_verdict(results, report_name=report_name)

        if args.output_json:
            print(json.dumps(outcome, ensure_ascii=False, indent=2))

        # 0이 아닌 종료 코드는 콜백을 의미하므로 편리합니다. CI/스크립트 판단
        sys.exit(0 if outcome['verdict'] == 'PASS' else 1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
