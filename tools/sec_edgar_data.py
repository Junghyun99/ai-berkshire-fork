#!/usr/bin/env python3
"""SEC EDGAR 재무 데이터 도구 — 미국 상장사의 공시 원본 재무제표(XBRL), 외부 종속성 없음(stdlib만).

financial-data 규범에서 미국 주식의 원본 1차 자료는 SEC EDGAR다. 이 도구는 EDGAR의
companyfacts API에서 손익·재무상태·현금흐름 핵심 계정을 가져온다.

시점 통제(--as-of):
  EDGAR는 모든 수치에 '공시일(filed)'을 붙여 준다. --as-of 날짜를 주면 그날까지 공시된 값만,
  그것도 그 시점에 유효했던 값(이후 정정 전)으로 보여준다. 예: 애플 2008년 총자산은 2010년
  정정 공시 전까지 396억 달러였고, 정정 후 362억 달러가 됐다. 백테스트·과거 시점 리서치에서
  미래 정보가 섞이지 않게 하는 핵심 장치다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)
  tradingagents/dataflows/vendors/sec_edgar.py 를 stdlib로 이식.

사전 준비:
  키는 필요 없다. 단, SEC는 User-Agent에 연락 가능한 이메일이 없으면 요청을 거부(403)한다.
      export SEC_EDGAR_USER_AGENT="이름 your@email.com"
  미설정 시 자리표시 주소로 요청한다(동작은 하지만 본인 주소로 바꾸길 권장). 초당 10회 이하 권장.

사용법:
    python3 tools/sec_edgar_data.py financials AAPL                         # 연간, 손익·재무상태·현금흐름 전부
    python3 tools/sec_edgar_data.py financials AAPL --statement income      # 손익만
    python3 tools/sec_edgar_data.py financials AAPL --freq quarterly        # 분기
    python3 tools/sec_edgar_data.py financials AAPL --as-of 2015-06-30      # 2015-06-30 시점에 공개돼 있던 값
    python3 tools/sec_edgar_data.py filings AAPL                            # 최근 10-K/10-Q/8-K 목록
    python3 tools/sec_edgar_data.py resolve AAPL                            # 티커 → CIK

한계:
  - 미국 SEC 등록 기업만(ADR 중 20-F 제출사 일부 포함). us-gaap 태그가 없는 IFRS 제출사는 데이터 없음.
  - 4분기 단독 수치는 만들지 않는다. 연간에서 3개 분기를 빼면 어떤 공시에도 없는 숫자가 되기 때문.
  - 분기 현금흐름은 10-Q가 누계(6개월·9개월)로만 공시하는 경우가 많다. 그때는 기간을 표시해 누계로 보여준다.

종료 코드: 0 정상 / 3 데이터 없음 / 4 출처 장애 (tools/_us_common.py 참고)
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import os
from datetime import date

from _us_common import (
    NoDataError, fmt_usd_millions, get_json, parse_as_of, read_cache, run, write_cache,
)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# 공시 이력은 새 공시가 나와야 바뀌므로 하루 한 번만 받아도 충분하다.
_CACHE_TTL = 24 * 60 * 60

# 계정별 XBRL 태그 후보(우선순위 순). 첫 번째로 매칭되는 태그를 쓰고, 태그끼리 합산하지 않는다.
# 같은 매출을 두 태그로 보고하는 회사가 있어 합산하면 이중 계산된다.
# 회사들이 연도별로 태그 이름을 바꿨기 때문에, 한 기간은 그 기간을 보고한 첫 태그 값을 쓴다.
_STATEMENTS = {
    "income": [
        ("매출", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")),
        ("매출원가", ("CostOfRevenue", "CostOfGoodsAndServicesSold")),
        ("매출총이익", ("GrossProfit",)),
        ("영업이익", ("OperatingIncomeLoss",)),
        ("순이익", ("NetIncomeLoss",)),
        ("희석EPS", ("EarningsPerShareDiluted",)),
    ],
    "balance": [
        ("자산총계", ("Assets",)),
        ("유동자산", ("AssetsCurrent",)),
        ("현금성자산", ("CashAndCashEquivalentsAtCarryingValue",)),
        ("부채총계", ("Liabilities",)),
        ("유동부채", ("LiabilitiesCurrent",)),
        ("자본총계", ("StockholdersEquity",
                   "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
    ],
    "cashflow": [
        ("영업현금흐름", ("NetCashProvidedByUsedInOperatingActivities",
                     "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")),
        ("투자현금흐름", ("NetCashProvidedByUsedInInvestingActivities",)),
        ("재무현금흐름", ("NetCashProvidedByUsedInFinancingActivities",)),
        ("설비투자(CapEx)", ("PaymentsToAcquirePropertyPlantAndEquipment",
                         "PaymentsToAcquireProductiveAssets")),
    ],
}
_TITLES = {"income": "손익계산서", "balance": "재무상태표", "cashflow": "현금흐름표"}

# 기간(일수) 범위. 한 공시가 같은 종료일로 '분기'와 '연초 누계'를 함께 보고하므로,
# 종료일만으로 매칭하면 반기 수치를 분기로 착각할 수 있다.
_SPANS = {"quarterly": (60, 115), "annual": (300, 400)}
# 10-Q 현금흐름은 누계로만 공시되는 경우가 많다: (최소일, 최대일, 개월수)
_YEAR_TO_DATE = ((150, 200, 6), (240, 290, 9))
# 연간 수치는 연간 보고서가 다룬 기간이어야 한다. 일부 10-Q가 12개월 합계를 보고해 기간 검사를 통과하기 때문.
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")


def _user_agent() -> str:
    """SEC는 연락처 없는 User-Agent를 403으로 거부한다."""
    configured = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    return configured or "ai-berkshire-fork research (contact@example.com)"


def _cached_json(url: str, name: str) -> dict:
    data = read_cache(name, _CACHE_TTL)
    if data is None:
        data = get_json(url, headers={"User-Agent": _user_agent()})
        write_cache(name, data)
    return data


def resolve(ticker: str):
    """티커 → (CIK 10자리, 회사명). SEC 등록사가 아니면 NoDataError."""
    table = _cached_json(_TICKERS_URL, "sec_company_tickers.json")
    wanted = ticker.strip().upper()
    for entry in table.values():
        if str(entry.get("ticker", "")).upper() == wanted:
            return f"{int(entry['cik_str']):010d}", entry.get("title", "")
    raise NoDataError(f"{wanted} 는 SEC EDGAR 티커 목록에 없습니다(미국 SEC 등록사가 아님).")


def _span_index(fact: dict, spans) -> object:
    """duration 사실이 spans 중 어느 기간인지(instant 사실은 0), 해당 없으면 None."""
    if "start" not in fact:
        return 0
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return next((i for i, (low, high) in enumerate(spans) if low <= days <= high), None)


def values_as_of(facts: dict, tags, as_of: str, spans, forms=()) -> tuple:
    """({(기간 종료일, 기간 인덱스): 값}, 단위) — as_of 시점에 알려져 있던 값.

    같은 기간이 여러 번 공시됐으면 as_of 이전의 '가장 늦은 공시'를 쓴다. 정정 공시는 그 공시일부터 반영된다.
    단위는 공시에서 가져온다(대부분 USD, EPS는 USD/shares — 똑같이 백만 단위로 나누면 0으로 찍힌다).
    """
    values = {}
    chosen_unit = "USD"
    for tag in tags:
        for unit, unit_values in ((facts.get(tag) or {}).get("units", {})).items():
            latest = {}
            covered = set()  # forms에 해당하는 공시가 보고한 기간
            for fact in unit_values:
                index = _span_index(fact, spans)
                key = (fact["end"], index)
                if fact["filed"] > as_of or index is None or key in values:
                    continue
                if not forms or fact.get("form", "").startswith(forms):
                    covered.add(key)
                seen = latest.get(key)
                if seen is None or fact["filed"] >= seen["filed"]:
                    latest[key] = fact
            latest = {k: f for k, f in latest.items() if k in covered}
            if latest:
                chosen_unit = unit
                values.update({k: f["val"] for k, f in latest.items()})
    return dict(sorted(values.items())), chosen_unit


def statement_table(us_gaap: dict, kind: str, freq: str, as_of: str) -> tuple:
    """(행 목록 [(기간 라벨, {계정: 값})], {계정: 단위}, 미태깅 계정 목록)."""
    if freq == "quarterly":
        spans = (_SPANS["quarterly"],) + tuple((lo, hi) for lo, hi, _ in _YEAR_TO_DATE)
        names = [""] + [f" ({m}개월 누계)" for _, _, m in _YEAR_TO_DATE]
        forms = ()
    else:
        spans, names, forms = (_SPANS["annual"],), [""], _ANNUAL_FORMS

    lines = {label: values_as_of(us_gaap, tags, as_of, spans, forms)
             for label, tags in _STATEMENTS[kind]}
    # 각 계정은 기간마다 가장 짧은 span을 쓴다: 분기 값이 있으면 분기, 없으면 누계.
    chosen = {label: {} for label in lines}
    for label, (vals, _) in lines.items():
        for end, index in vals:
            chosen[label][end] = min(index, chosen[label].get(end, index))
    periods = sorted({(end, idx) for per in chosen.values() for end, idx in per.items()})

    tagged = {label: line for label, line in lines.items() if line[0]}
    # 태그가 아예 없는 계정만 '미태깅'. 태그는 있는데 as_of까지 공시가 없으면 미태깅이 아니다.
    untagged = [label for label, tags in _STATEMENTS[kind] if not any(t in us_gaap for t in tags)]
    rows = []
    for end, index in periods:
        row = {}
        for label, (vals, _) in tagged.items():
            row[label] = vals.get((end, index)) if chosen[label].get(end) == index else None
        rows.append((end + names[index], row))
    units = {label: unit for label, (_, unit) in tagged.items()}
    return rows, units, untagged


def _fmt_cell(value, unit: str) -> str:
    if value is None:
        return "-"
    return fmt_usd_millions(value) if unit == "USD" else f"{value:.2f}"


def _load_us_gaap(ticker: str):
    cik, name = resolve(ticker)
    facts = _cached_json(_FACTS_URL.format(cik=cik), f"sec_CIK{cik}.json")
    us_gaap = (facts.get("facts") or {}).get("us-gaap")
    if not us_gaap:
        raise NoDataError(f"{ticker.upper()}({name}) 는 us-gaap XBRL 데이터가 없습니다(IFRS 제출사일 수 있음).")
    return cik, name, us_gaap


def cmd_financials(ticker: str, statement: str, freq: str, as_of: str, limit: int):
    cik, name, us_gaap = _load_us_gaap(ticker)
    kinds = list(_STATEMENTS) if statement == "all" else [statement]
    freq_label = "연간" if freq == "annual" else "분기"

    print("=" * 72)
    print(f"SEC EDGAR 재무제표: {name} ({ticker.upper()}) — {freq_label} | CIK {cik}")
    print(f"시점: {as_of} 까지 공시된 값(그 시점 기준, 이후 정정 미반영)")
    print("단위: 백만 달러(USD). EPS 등 USD가 아닌 계정은 열 이름에 단위 표기")
    print("=" * 72)

    by_period = {}  # 파생 지표용: 기간 → 모든 계정 값(같은 기간 값끼리만 계산하기 위함)
    any_rows = False
    for kind in kinds:
        rows, units, untagged = statement_table(us_gaap, kind, freq, as_of)
        print(f"\n[{_TITLES[kind]}]")
        if untagged:
            print(f"  이 회사가 태깅하지 않은 계정: {', '.join(untagged)}")
        if not rows:
            print(f"  {as_of} 까지 공시된 {freq_label} 데이터 없음")
            continue
        any_rows = True
        rows = rows[-limit:]
        labels = list(units)
        header = ["기간"] + [lb if units[lb] == "USD" else f"{lb}({units[lb]})" for lb in labels]
        print("  " + " | ".join(header))
        for period, row in rows:
            print("  " + " | ".join([period] + [_fmt_cell(row.get(lb), units[lb]) for lb in labels]))
        for period, row in rows:
            by_period.setdefault(period, {}).update({lb: v for lb, v in row.items() if v is not None})

    if not any_rows:
        raise NoDataError(f"{ticker.upper()} 의 {freq_label} 재무 데이터가 {as_of} 까지 공시된 것이 없습니다.")

    if freq == "annual" and statement == "all":
        with_revenue = [pd for pd in sorted(by_period) if by_period[pd].get("매출")]
        if with_revenue:
            _print_derived(with_revenue[-1], by_period[with_revenue[-1]])

    print("\n  출처: SEC EDGAR XBRL companyfacts(data.sec.gov) — 1차 공시 원본.")
    print("  교차 검증: stockanalysis(curl 기본 User-Agent) 또는 "
          f"python3 tools/global_stock_data.py financials {ticker.upper()} (Yahoo, 부 출처). 오차 >1% 시 표기.")


def _print_derived(period: str, a: dict):
    """최신 연간 기준 파생 지표. 같은 기간 값끼리만 계산한다."""
    rev, gp, op, ni = a.get("매출"), a.get("매출총이익"), a.get("영업이익"), a.get("순이익")
    eq, li = a.get("자본총계"), a.get("부채총계")
    ocf, capex = a.get("영업현금흐름"), a.get("설비투자(CapEx)")
    print(f"\n[파생 지표 — {period} 기준, 단순 계산]")
    if rev:
        if gp is not None:
            print(f"  매출총이익률:   {gp / rev * 100:.1f}%")
        if op is not None:
            print(f"  영업이익률:     {op / rev * 100:.1f}%")
        if ni is not None:
            print(f"  순이익률:       {ni / rev * 100:.1f}%")
    if eq and ni is not None:
        print(f"  ROE(기말자본):  {ni / eq * 100:.1f}%")
    if eq and li is not None:
        print(f"  부채비율:       {li / eq * 100:.1f}% (부채총계/자본총계)")
    if ocf is not None and capex is not None:
        print(f"  FCF:            {fmt_usd_millions(ocf - capex)} 백만 달러 (영업현금흐름 - CapEx)")
        if ni:
            print(f"  영업현금흐름/순이익: {ocf / ni:.2f}")


def cmd_filings(ticker: str, forms: str, count: int, as_of: str):
    cik, name = resolve(ticker)
    data = _cached_json(_SUBMISSIONS_URL.format(cik=cik), f"sec_submissions_CIK{cik}.json")
    recent = (data.get("filings") or {}).get("recent") or {}
    wanted = {f.strip().upper() for f in forms.split(",") if f.strip()}
    rows = []
    for i, form in enumerate(recent.get("form", [])):
        filed = recent["filingDate"][i]
        if filed > as_of or (wanted and form.upper() not in wanted):
            continue
        accession = recent["accessionNumber"][i]
        doc = recent.get("primaryDocument", [""] * (i + 1))[i]
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{accession.replace('-', '')}/{doc}") if doc else ""
        rows.append((filed, form, recent.get("reportDate", [""] * (i + 1))[i], url))
        if len(rows) >= count:
            break
    if not rows:
        raise NoDataError(f"{ticker.upper()} 의 {sorted(wanted) or '전체'} 공시가 {as_of} 까지 없습니다.")
    print("=" * 72)
    print(f"SEC EDGAR 공시 목록: {name} ({ticker.upper()}) | CIK {cik} | {as_of} 까지")
    print("=" * 72)
    for filed, form, report, url in rows:
        print(f"  [{filed}] {form:<8} 대상기간 {report or '-':<10} {url}")


def cmd_resolve(ticker: str):
    cik, name = resolve(ticker)
    print(f"{ticker.upper()} → CIK {cik} ({name})")


def main():
    p = argparse.ArgumentParser(description="SEC EDGAR 재무 데이터 도구(미국 상장사, 공시 원본).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("financials", help="손익·재무상태·현금흐름 핵심 계정")
    pf.add_argument("ticker", help="미국 티커(예: AAPL)")
    pf.add_argument("--statement", default="all", choices=["all", "income", "balance", "cashflow"])
    pf.add_argument("--freq", default="annual", choices=["annual", "quarterly"])
    pf.add_argument("--as-of", default="", help="이 날짜까지 공시된 값만(YYYY-MM-DD, 기본 오늘)")
    pf.add_argument("--limit", type=int, default=0, help="최근 N개 기간(기본 연간 5, 분기 8)")

    pl = sub.add_parser("filings", help="공시 목록(10-K/10-Q/8-K 등)")
    pl.add_argument("ticker")
    pl.add_argument("--forms", default="10-K,10-Q,8-K,20-F,DEF 14A", help="쉼표 구분, 빈 값이면 전체")
    pl.add_argument("--count", type=int, default=15)
    pl.add_argument("--as-of", default="")

    pr = sub.add_parser("resolve", help="티커 → CIK")
    pr.add_argument("ticker")

    args = p.parse_args()
    if args.cmd == "financials":
        limit = args.limit or (5 if args.freq == "annual" else 8)
        cmd_financials(args.ticker, args.statement, args.freq, parse_as_of(args.as_of), limit)
    elif args.cmd == "filings":
        cmd_filings(args.ticker, args.forms, args.count, parse_as_of(args.as_of))
    elif args.cmd == "resolve":
        cmd_resolve(args.ticker)


if __name__ == "__main__":
    run(main)
