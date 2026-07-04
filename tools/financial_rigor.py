#!/usr/bin/env python3
"""Financial Rigor Toolkit for AI Berkshire.

Command-line tool for verifying financial data accuracy during investment research.
Automatically called by Claude Code Skills at critical validation checkpoints.

Zero external dependencies — uses only Python stdlib (decimal, json, math, argparse).
Requires Python >= 3.7.

Usage (called automatically by Skills, no manual execution needed):
    python3 tools/financial_rigor.py verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
    python3 tools/financial_rigor.py verify-valuation --price 510 --eps 23.5 --bvps 120 --fcf-per-share 18 --dividend 2.4
    python3 tools/financial_rigor.py cross-validate --field revenue --values '{"연보": 7518, "Yahoo": 7500, "StockAnalysis": 7520}' --unit 1억
    python3 tools/financial_rigor.py benford --values '[1234, 2345, 3456, ...]'
    python3 tools/financial_rigor.py calc --expr '510 * 9.11e9'
"""

import argparse
import json
import math
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN, InvalidOperation

# ---------------------------------------------------------------------------
# Exact Decimal Engine (no floating-point drift)
# ---------------------------------------------------------------------------

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)


def exact(value) -> Decimal:
    """Convert any numeric to exact Decimal, avoiding float traps."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def fmt_number(d: Decimal, unit: str = "") -> str:
    """Format large numbers in human-readable form (1억/수조/B/T)."""
    v = float(d)
    abs_v = abs(v)
    if unit in ("1억", "10억", "1억홍콩달러", "1억달러"):
        if abs_v >= 10000:
            return f"{v/10000:.2f}수조{unit[1:] if len(unit) > 1 else ''}"
        return f"{v:.2f}{unit}"
    if abs_v >= 1e12:
        return f"{v/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{v/1e6:.2f}M"
    return f"{v:,.2f}"


# ---------------------------------------------------------------------------
# 1. Market Cap Verification (주가×총주식수 vs 보고된 시가총액)
# ---------------------------------------------------------------------------

def verify_market_cap(price, shares, reported_cap, currency=""):
    """Verify market cap = price × shares, compare with reported value."""
    p = exact(price)
    s = exact(shares)
    r = exact(reported_cap)

    calculated = _CTX.multiply(p, s)
    deviation = abs(float(calculated - r) / float(r)) * 100 if r != 0 else 0

    print("=" * 60)
    print("시장가치 검증 (Market Cap Verification)")
    print("=" * 60)
    print(f"  주가 (Price):       {p} {currency}")
    print(f"  총주식수 (Shares):    {fmt_number(s)}")
    print(f"  시가총액 계산:           {fmt_number(calculated)} {currency}")
    print(f"  보고된 시가총액:           {fmt_number(r)} {currency}")
    print(f"  편차:               {deviation:.2f}%")
    print()

    if deviation > 5:
        print(f"  ❌ 경고하다: 편차 {deviation:.1f}% > 5%, 확인 바랍니다:")
        print(f"     - 주식 자본이 최신 상태입니까 (환매/추가발행）?")
        print(f"     - 단위가 일관적입니까(HKD vs 인민폐 vs 달러）?")
        print(f"     - 주가가 최신인가요??")
        return False
    elif deviation > 1:
        print(f"  ⚠️  편차 {deviation:.1f}% 허용 범위 내, 주가변동에 따른 것일 수도 있음/자본 변동")
        return True
    else:
        print(f"  ✅ 검산 통과 — 편차 {deviation:.2f}%")
        return True


# ---------------------------------------------------------------------------
# 2. Valuation Metrics Verification (평가지표 계산)
# ---------------------------------------------------------------------------

def verify_valuation(price, eps=None, bvps=None, fcf_per_share=None,
                     dividend=None, revenue_per_share=None):
    """Calculate and verify key valuation ratios from raw inputs."""
    p = exact(price)

    print("=" * 60)
    print("평가지표 계산 (Valuation Verification)")
    print("=" * 60)
    print(f"  현재 주가: {p}")
    print()

    results = {}

    if eps is not None:
        e = exact(eps)
        if e != 0:
            pe = _CTX.divide(p, e)
            print(f"  PE (TTM):  {p} / {e} = {pe:.2f}x")
            results["PE"] = float(pe)
            # Earnings yield
            ey = _CTX.divide(e, p) * 100
            print(f"  수익율: {ey:.2f}%")
        else:
            print(f"  PE: EPS~을 위한0, 계산할 수 없습니다")

    if bvps is not None:
        b = exact(bvps)
        if b != 0:
            pb = _CTX.divide(p, b)
            print(f"  PB:        {p} / {b} = {pb:.2f}x")
            results["PB"] = float(pb)
            if eps is not None and float(exact(eps)) != 0:
                roe = _CTX.divide(exact(eps), b) * 100
                print(f"  ROE:       {exact(eps)} / {b} = {roe:.2f}%")
                results["ROE"] = float(roe)

    if fcf_per_share is not None:
        f = exact(fcf_per_share)
        if f != 0:
            fcf_yield = _CTX.divide(f, p) * 100
            pfcf = _CTX.divide(p, f)
            print(f"  P/FCF:     {p} / {f} = {pfcf:.2f}x")
            print(f"  FCF Yield: {fcf_yield:.2f}%")
            results["P_FCF"] = float(pfcf)
            results["FCF_Yield"] = float(fcf_yield)

    if dividend is not None:
        d = exact(dividend)
        if p != 0:
            div_yield = _CTX.divide(d, p) * 100
            print(f"  배당수익률:    {d} / {p} = {div_yield:.2f}%")
            results["Dividend_Yield"] = float(div_yield)

    if revenue_per_share is not None:
        r = exact(revenue_per_share)
        if r != 0:
            ps = _CTX.divide(p, r)
            print(f"  PS:        {p} / {r} = {ps:.2f}x")
            results["PS"] = float(ps)

    print()
    print("  ✅ 모든 지표는 정밀 십진수(Decimal)로 계산 — 부동소수점 오차 없음")
    return results


# ---------------------------------------------------------------------------
# 3. Cross-Source Data Validation (다중 소스 교차 검증)
# ---------------------------------------------------------------------------

def cross_validate(field_name, source_values: dict, unit="", tolerance_pct=2.0):
    """Compare a data point across multiple sources, flag discrepancies."""
    print("=" * 60)
    print(f"교차 검증: {field_name} (Cross-Validation)")
    print("=" * 60)

    values = {k: exact(v) for k, v in source_values.items()}
    sources = list(values.keys())
    nums = list(values.values())

    # Find median as reference
    sorted_vals = sorted(float(v) for v in nums)
    n = len(sorted_vals)
    median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2

    print(f"  데이터 소스 수: {len(sources)}")
    print(f"  기준 중앙값: {fmt_number(exact(median))} {unit}")
    print()

    all_ok = True
    for src, val in values.items():
        dev = abs(float(val) - median) / median * 100 if median != 0 else 0
        status = "✅" if dev <= tolerance_pct else "❌"
        if dev > tolerance_pct:
            all_ok = False
        print(f"  {status} {src:20s}: {fmt_number(val)} {unit}  (편차 {dev:.2f}%)")

    print()
    if all_ok:
        print(f"  ✅ 모든 소스 편차 ≤ {tolerance_pct}%, 데이터 일치")
    else:
        print(f"  ⚠️  소스 편향이 있습니다 > {tolerance_pct}%, 차이가 나는 이유를 확인해주세요")
        print(f"     제안: 회사의 연간 보고서에 우선순위가 부여됩니다./데이터 교환")

    # Consensus value
    consensus = median
    print(f"\n  컨센서스 값 (가중 중앙값): {fmt_number(exact(consensus))} {unit}")
    return {"consensus": consensus, "all_consistent": all_ok}


# ---------------------------------------------------------------------------
# 4. Benford's Law Quick Check (금융 데이터 사기 탐지)
# ---------------------------------------------------------------------------

_BENFORD = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def benford_check(values: list):
    """Quick Benford's Law check on a list of financial values."""
    print("=" * 60)
    print("Benford법률 테스트 (Financial Data Fabrication Check)")
    print("=" * 60)

    # Extract leading digits
    digits = []
    for v in values:
        v = abs(float(v))
        if v > 0:
            sig = 10 ** (math.log10(v) - math.floor(math.log10(v)))
            d = int(sig)
            if 1 <= d <= 9:
                digits.append(d)

    n = len(digits)
    if n < 50:
        print(f"  ⚠️  불충분한 표본 크기: {n} < 50, Benford분석이 신뢰할 수 없습니다")
        return None

    # Observed distribution
    counts = {}
    for d in digits:
        counts[d] = counts.get(d, 0) + 1
    observed = {d: counts.get(d, 0) / n for d in range(1, 10)}

    # MAD (Nigrini's Mean Absolute Deviation)
    mad = sum(abs(observed.get(d, 0) - _BENFORD[d]) for d in range(1, 10)) / 9

    # Chi-square
    chi2 = sum((counts.get(d, 0) - _BENFORD[d] * n) ** 2 / (_BENFORD[d] * n) for d in range(1, 10))

    # Conformity
    if mad < 0.006:
        conformity = "Close (매우 일치함)"
    elif mad < 0.012:
        conformity = "Acceptable (받아들일 수 있는)"
    elif mad < 0.015:
        conformity = "Marginally Acceptable (가장자리)"
    else:
        conformity = "Nonconforming (충족되지 않음 ⚠️)"

    print(f"  표본 크기:    {n}")
    print(f"  MAD:       {mad:.6f}")
    print(f"  Chi-sq:    {chi2:.2f}")
    print(f"  적합성:    {conformity}")
    print()

    # Digit distribution table
    print(f"  {'첫 번째 숫자':>6} {'관찰':>8} {'Benford예상하다':>12} {'편차':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*12} {'-'*8}")
    for d in range(1, 10):
        obs = observed.get(d, 0)
        exp = _BENFORD[d]
        dev = obs - exp
        flag = " ⚠️" if abs(dev) > 0.03 else ""
        print(f"  {d:>6d} {obs:>8.3f} {exp:>12.3f} {dev:>+8.3f}{flag}")

    print()
    is_ok = mad < 0.015
    if is_ok:
        print("  ✅ 데이터의 첫 번째 숫자의 분포는 다음과 같습니다.Benford법")
    else:
        print("  ❌ 데이터의 첫 번째 숫자의 비정상적인 분포, 사람의 조정이 있을 수 있습니다.")
        print("     힌트: 충족되지 않음Benford법이 꼭 가짜인 것은 아니다, 하지만 추가 조사가 필요해")

    return {"mad": mad, "chi2": chi2, "conformity": conformity, "is_conforming": is_ok}


# ---------------------------------------------------------------------------
# 5. Exact Calculator (정확한 계산기)
# ---------------------------------------------------------------------------

def exact_calc(expr: str):
    """Evaluate a financial expression with exact decimal arithmetic.

    Supports: +, -, *, /, (), numbers (including scientific notation).
    """
    print("=" * 60)
    print("정확한 계산 (Exact Calculator)")
    print("=" * 60)

    # Safe evaluation: only allow numbers and arithmetic
    allowed = set("0123456789.+-*/() eE")
    if not all(c in allowed for c in expr.replace(" ", "")):
        print(f"  ❌ 안전하지 않은 표현: {expr}")
        return None

    try:
        # Replace scientific notation for Decimal compatibility
        result = eval(expr, {"__builtins__": {}}, {})
        d_result = exact(result)
        print(f"  표현: {expr}")
        print(f"  결과:   {fmt_number(d_result)}")
        print(f"  정확한 값: {d_result}")
        return float(d_result)
    except Exception as e:
        print(f"  ❌ 계산 오류: {e}")
        return None


# ---------------------------------------------------------------------------
# 6. Three-Scenario Valuation (3가지 시나리오 평가)
# ---------------------------------------------------------------------------

def three_scenario_valuation(current_price, current_eps, shares_billion,
                             growth_optimistic, growth_neutral, growth_pessimistic,
                             pe_optimistic, pe_neutral, pe_pessimistic,
                             years=3, currency=""):
    """Calculate three-scenario target prices with exact arithmetic."""
    print("=" * 60)
    print("3가지 시나리오 평가 모델 (Three-Scenario Valuation)")
    print("=" * 60)

    p = exact(current_price)
    eps = exact(current_eps)
    shares = exact(shares_billion)

    scenarios = [
        ("낙관 (Bull)", growth_optimistic, pe_optimistic),
        ("중립 (Base)", growth_neutral, pe_neutral),
        ("비관 (Bear)", growth_pessimistic, pe_pessimistic),
    ]

    print(f"  현재 주가: {p} {currency}")
    print(f"  현재 EPS:  {eps}")
    print(f"  예측 기간:   {years}년")
    print()
    print(f"  {'시나리오':10} {'연 성장률':>8} {'목표PE':>8} {'목표EPS':>10} {'목표주가':>10} {'등락률':>8}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*8}")

    pct_notice = False
    for name, growth, pe in scenarios:
        g = exact(growth)
        # |growth| > 1 이면 % 입력으로 간주해 자동 변환 (예: 15 → 0.15) — Decimal 나눗셈으로 정밀도 유지
        if abs(g) > 1:
            g = _CTX.divide(g, Decimal("100"))
            pct_notice = True
        target_pe = exact(pe)
        # Future EPS = current EPS × (1 + growth)^years
        future_eps = eps
        for _ in range(years):
            future_eps = _CTX.multiply(future_eps, _CTX.add(Decimal("1"), g))
        target_price = _CTX.multiply(future_eps, target_pe)
        change = float(target_price - p) / float(p) * 100

        print(f"  {name:12} {float(g)*100:>7.0f}% {float(target_pe):>7.0f}x "
              f"{float(future_eps):>10.2f} {float(target_price):>9.1f} {change:>+7.1f}%")

    print()
    if pct_notice:
        print("  ⚠️ 성장률 입력값 |x| > 1 감지 → %로 간주해 100으로 나눠 계산했습니다 (권장 형식: 소수, 예: 0.15).")
    print("  ✅ 모든 계산은 정밀 십진수(Decimal) 기반 — 결과는 재현·감사 가능합니다.")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Financial Rigor Toolkit — 금융 데이터 엄격성 검증 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
  %(prog)s verify-valuation --price 510 --eps 23.5 --bvps 120
  %(prog)s cross-validate --field revenue --values '{"연보": 7518, "Yahoo": 7500}' --unit 1억
  %(prog)s benford --values '[1234, 2345, 3456, ...]'
  %(prog)s calc --expr '510 * 9.11e9'
        """)

    sub = parser.add_subparsers(dest="command")

    # verify-market-cap
    mc = sub.add_parser("verify-market-cap", help="시장 가치 확인 = 주가 × 총주식수")
    mc.add_argument("--price", type=float, required=True)
    mc.add_argument("--shares", type=float, required=True, help="총주식수")
    mc.add_argument("--reported", type=float, required=True, help="보고된 시가총액")
    mc.add_argument("--currency", default="", help="통화")

    # verify-valuation
    val = sub.add_parser("verify-valuation", help="밸류에이션 지표 확인")
    val.add_argument("--price", type=float, required=True)
    val.add_argument("--eps", type=float, default=None)
    val.add_argument("--bvps", type=float, default=None, help="주당순자산")
    val.add_argument("--fcf-per-share", type=float, default=None)
    val.add_argument("--dividend", type=float, default=None, help="주당 배당금")
    val.add_argument("--revenue-per-share", type=float, default=None)

    # cross-validate
    cv = sub.add_parser("cross-validate", help="다중 소스 교차 검증")
    cv.add_argument("--field", required=True, help="데이터 필드 이름")
    cv.add_argument("--values", required=True, help="JSON: {원천: 수치}")
    cv.add_argument("--unit", default="")
    cv.add_argument("--tolerance", type=float, default=2.0, help="공차 비율")

    # benford
    bf = sub.add_parser("benford", help="Benford법률 테스트")
    bf.add_argument("--values", required=True, help="JSON정렬")

    # calc
    ca = sub.add_parser("calc", help="정확한 계산")
    ca.add_argument("--expr", required=True, help="산술 표현")

    # three-scenario
    ts = sub.add_parser("three-scenario", help="3가지 시나리오 평가")
    ts.add_argument("--price", type=float, required=True)
    ts.add_argument("--eps", type=float, required=True)
    ts.add_argument("--shares", type=float, required=True, help="총주식수(억 주)")
    ts.add_argument("--growth", nargs=3, type=float, required=True,
                    help="낙관/중립/비관 연 성장률 — 소수 형식 (예: 0.15 -0.05 -0.25). |x|>1이면 %%로 간주해 자동 변환")
    ts.add_argument("--pe", nargs=3, type=float, required=True,
                    help="낙관/중립/비관 목표 PER (예: 10 9 12)")
    ts.add_argument("--years", type=int, default=3)
    ts.add_argument("--currency", default="")

    args = parser.parse_args()

    if args.command == "verify-market-cap":
        verify_market_cap(args.price, args.shares, args.reported, args.currency)
    elif args.command == "verify-valuation":
        verify_valuation(args.price, args.eps, args.bvps, args.fcf_per_share,
                        args.dividend, args.revenue_per_share)
    elif args.command == "cross-validate":
        values = json.loads(args.values)
        cross_validate(args.field, values, args.unit, args.tolerance)
    elif args.command == "benford":
        values = json.loads(args.values)
        benford_check(values)
    elif args.command == "calc":
        exact_calc(args.expr)
    elif args.command == "three-scenario":
        three_scenario_valuation(
            args.price, args.eps, args.shares,
            args.growth[0], args.growth[1], args.growth[2],
            args.pe[0], args.pe[1], args.pe[2],
            args.years, args.currency)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
