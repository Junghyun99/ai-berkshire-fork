#!/usr/bin/env python3
"""글로벌 주식 데이터 도구 — Yahoo Finance 기반, 외부 종속성 없음(stdlib만).

한국(KOSPI/KOSDAQ)·미국·홍콩 등 Yahoo Finance가 커버하는 전 시장의
실시간 시세, 핵심 재무 데이터, 밸류에이션 지표를 제공한다.
중국 A주는 기존 tools/ashare_data.py 를 사용한다(독립 모듈, 상호 영향 없음).

종목 코드 입력 규칙:
    005930          → 한국 주식. .KS(KOSPI) 우선 조회, 실패 시 .KQ(KOSDAQ) 자동 재시도
    035420.KS       → 접미사를 붙이면 그대로 사용
    AAPL, BRK-B     → 미국 주식 티커
    0700.HK / 700   → 홍콩 주식(숫자 1~5자리는 4자리로 패딩 후 .HK)

사용법(Skills에서 자동 호출 기준):
    python3 tools/global_stock_data.py quote 005930         # 실시간 시세
    python3 tools/global_stock_data.py financials 005930    # 핵심 재무(최근 5년)
    python3 tools/global_stock_data.py valuation 005930     # 밸류에이션 지표 + 시총 검산
    python3 tools/global_stock_data.py search "samsung"     # 종목 코드 검색(영문명/티커만, 한글 미지원)

필요 Python >= 3.8, 외부 종속성 없음.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from urllib.parse import urlencode

_TIMEOUT = 15
_BASE = "https://query1.finance.yahoo.com"


def _curl(url):
    """curl로 직접 요청(시스템 프록시 설정을 그대로 따른다)."""
    result = subprocess.run(
        ["curl", "-s",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         url],
        capture_output=True, timeout=_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"요청 실패: {url}")
    return result.stdout.decode("utf-8")


def _get_json(path, params=None):
    url = f"{_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return json.loads(_curl(url))


# ---------------------------------------------------------------------------
# 종목 코드 정규화
# ---------------------------------------------------------------------------

def _candidates(code: str):
    """입력 코드를 Yahoo Finance 심볼 후보 목록으로 변환."""
    code = code.strip().upper()
    if re.fullmatch(r"\d{6}", code):
        return [f"{code}.KS", f"{code}.KQ"]        # 한국: KOSPI 우선, KOSDAQ 재시도
    if re.fullmatch(r"\d{1,5}", code):
        return [f"{int(code):04d}.HK"]              # 홍콩: 4자리 패딩
    return [code]                                   # 이미 접미사 있음 / 미국 티커 등


def _fetch_meta(symbol: str):
    """v8 chart API의 meta에서 시세 스냅샷을 얻는다."""
    data = _get_json(f"/v8/finance/chart/{symbol}",
                     {"range": "1d", "interval": "1d"})
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        return None
    return result.get("meta")


def _resolve(code: str):
    """후보 심볼을 순서대로 시도해 (심볼, meta) 반환. 전부 실패하면 (None, None).

    주의: KOSDAQ 종목을 .KS로 조회해도 가격이 응답되지만 잘못된 데이터가
    온다(이름 없음, 가격 상이). 따라서 longName이 있는 응답을 정상으로
    우선하고, longName이 있는 후보가 하나도 없을 때만 가격만 있는 응답을 쓴다.
    """
    weak = None
    for symbol in _candidates(code):
        try:
            meta = _fetch_meta(symbol)
        except (ConnectionError, json.JSONDecodeError):
            meta = None
        if not meta or meta.get("regularMarketPrice") is None:
            continue
        if meta.get("longName"):
            return symbol, meta
        if weak is None:
            weak = (symbol, meta)
    return weak if weak else (None, None)


# ---------------------------------------------------------------------------
# 재무/밸류에이션 timeseries API
# ---------------------------------------------------------------------------

def _timeseries(symbol: str, types):
    """fundamentals-timeseries API. {타입: [(날짜, 원시값), ...]} 반환(날짜 오름차순)."""
    now = int(time.time())
    data = _get_json(
        f"/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}",
        {"type": ",".join(types), "period1": now - 10 * 365 * 86400, "period2": now},
    )
    out = {}
    for r in data.get("timeseries", {}).get("result", []):
        t = r.get("meta", {}).get("type", [None])[0]
        if not t or t not in r:
            continue
        rows = [(v["asOfDate"], v["reportedValue"]["raw"])
                for v in r[t] if v and v.get("reportedValue")]
        out[t] = sorted(rows)
    return out


def _latest(ts, key):
    rows = ts.get(key) or []
    return rows[-1][1] if rows else None


# ---------------------------------------------------------------------------
# 포맷팅
# ---------------------------------------------------------------------------

def _fmt_big(value, currency: str) -> str:
    """통화별 큰 수 표기: KRW는 조/억, 그 외는 B/M."""
    if value is None:
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if currency == "KRW":
        if abs(v) >= 1e12:
            return f"{v / 1e12:,.2f}조원"
        if abs(v) >= 1e8:
            return f"{v / 1e8:,.1f}억원"
        return f"{v:,.0f}원"
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f}B {currency}"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f}M {currency}"
    return f"{v:,.0f} {currency}"


def _fmt_num(value, digits=2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except (ValueError, TypeError):
        return str(value)


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.1f}%"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------

def cmd_quote(code: str):
    """실시간 시세 스냅샷."""
    symbol, m = _resolve(code)
    if not m:
        print(f"❌ 종목을 찾을 수 없습니다: {code}")
        return

    cur = m.get("currency", "")
    price = m.get("regularMarketPrice")
    prev = m.get("chartPreviousClose")
    change_pct = (price - prev) / prev * 100 if price and prev else None

    print("=" * 60)
    print(f"실시간 시세: {m.get('longName') or m.get('shortName')} ({symbol})")
    print("=" * 60)
    print(f"  거래소:      {m.get('fullExchangeName', '-')} / 통화 {cur}")
    print(f"  현재가:      {_fmt_num(price)}")
    print(f"  등락률:      {_fmt_pct(change_pct)}")
    print(f"  전일종가:    {_fmt_num(prev)}")
    print(f"  당일고가:    {_fmt_num(m.get('regularMarketDayHigh'))}")
    print(f"  당일저가:    {_fmt_num(m.get('regularMarketDayLow'))}")
    print(f"  거래량:      {_fmt_num(m.get('regularMarketVolume'), 0)}주")
    print(f"  52주 최고:   {_fmt_num(m.get('fiftyTwoWeekHigh'))}")
    print(f"  52주 최저:   {_fmt_num(m.get('fiftyTwoWeekLow'))}")

    try:
        ts = _timeseries(symbol, ["trailingMarketCap", "trailingPeRatio", "trailingPbRatio"])
        print(f"  시가총액:    {_fmt_big(_latest(ts, 'trailingMarketCap'), cur)}")
        print(f"  PER(TTM):    {_fmt_num(_latest(ts, 'trailingPeRatio'))}")
        print(f"  PBR:         {_fmt_num(_latest(ts, 'trailingPbRatio'))}")
    except (ConnectionError, json.JSONDecodeError):
        print("  ⚠️ 시총/PER/PBR 조회 실패 — valuation 명령 또는 WebSearch로 보완 필요")


def cmd_valuation(code: str):
    """밸류에이션 지표 + 시가총액 검산(주가 × 발행주식수)."""
    symbol, m = _resolve(code)
    if not m:
        print(f"❌ 종목을 찾을 수 없습니다: {code}")
        return

    cur = m.get("currency", "")
    price = m.get("regularMarketPrice")
    ts = _timeseries(symbol, [
        "trailingMarketCap", "trailingPeRatio", "trailingPbRatio",
        "quarterlyMarketCap", "quarterlyPeRatio", "quarterlyPbRatio",
        "quarterlyShareIssued",
    ])
    market_cap = _latest(ts, "trailingMarketCap") or _latest(ts, "quarterlyMarketCap")
    shares = _latest(ts, "quarterlyShareIssued")

    print("=" * 60)
    print(f"밸류에이션 지표: {m.get('longName') or m.get('shortName')} ({symbol})")
    print("=" * 60)
    print(f"  현재가:      {_fmt_num(price)} {cur}")
    print(f"  시가총액:    {_fmt_big(market_cap, cur)}")
    print(f"  PER(TTM):    {_fmt_num(_latest(ts, 'trailingPeRatio'))}")
    print(f"  PBR:         {_fmt_num(_latest(ts, 'trailingPbRatio'))}")
    print(f"  발행주식수:  {_fmt_num(shares, 0)}주 (최근 분기 보고 기준)")
    print(f"  52주 최고:   {_fmt_num(m.get('fiftyTwoWeekHigh'))}")
    print(f"  52주 최저:   {_fmt_num(m.get('fiftyTwoWeekLow'))}")

    # 시가총액 검산: 주가 × 발행주식수 vs API 시총 (CLAUDE.md 수동 검산 원칙)
    if price and shares and market_cap:
        calc = price * shares
        diff = abs(calc - market_cap) / market_cap * 100
        mark = "✅ 일치" if diff <= 3 else "⚠️ 편차 큼 — 주식수 변동/데이터 시점 차이 확인 필요"
        print(f"\n  시총 검산:   주가 × 발행주식수 = {_fmt_big(calc, cur)}")
        print(f"               API 시총 대비 편차 {diff:.1f}% → {mark}")
    else:
        print("\n  ⚠️ 시총 검산 불가(주식수 또는 시총 데이터 없음)")


def cmd_financials(code: str):
    """최근 5년 핵심 재무 데이터(연간)."""
    symbol, m = _resolve(code)
    if not m:
        print(f"❌ 종목을 찾을 수 없습니다: {code}")
        return

    cur = m.get("currency", "")
    ts = _timeseries(symbol, [
        "annualTotalRevenue", "annualNetIncomeCommonStockholders",
        "annualDilutedEPS", "annualBasicEPS", "annualStockholdersEquity",
    ])
    revenue = dict(ts.get("annualTotalRevenue", []))
    profit = dict(ts.get("annualNetIncomeCommonStockholders", []))
    eps = dict(ts.get("annualDilutedEPS", []) or ts.get("annualBasicEPS", []))
    equity = dict(ts.get("annualStockholdersEquity", []))

    print("=" * 60)
    print(f"핵심 재무 데이터(연간): {m.get('longName') or m.get('shortName')} ({symbol})")
    print("=" * 60)

    dates = sorted(set(revenue) | set(profit))[-5:]
    if not dates:
        print("  ⚠️ 재무 데이터를 얻을 수 없습니다. WebSearch로 보완하세요.")
        return

    for i, d in enumerate(dates):
        rev, ni, eq = revenue.get(d), profit.get(d), equity.get(d)
        prev_d = dates[i - 1] if i > 0 else None
        print(f"\n  --- {d} 회계연도 ---")
        print(f"  매출:            {_fmt_big(rev, cur)}")
        if prev_d and rev and revenue.get(prev_d):
            print(f"  매출 성장률:     {_fmt_pct((rev / revenue[prev_d] - 1) * 100)}")
        print(f"  지배주주 순이익: {_fmt_big(ni, cur)}")
        if prev_d and ni and profit.get(prev_d):
            print(f"  순이익 성장률:   {_fmt_pct((ni / profit[prev_d] - 1) * 100)}")
        if eps.get(d) is not None:
            print(f"  희석 EPS:        {_fmt_num(eps[d])}")
        if ni and eq:
            print(f"  ROE(기말자본):   {ni / eq * 100:.1f}% (단순 계산: 순이익/기말 자기자본)")

    print("\n  주의: Yahoo Finance 집계 기준. 핵심 수치는 공시 원본(DART/HKEX/SEC)과 교차 검증할 것.")


def cmd_search(keyword: str):
    """종목 코드 검색. 한글 종목명은 Yahoo가 지원하지 않음 — 영문명/티커로 검색."""
    if re.search(r"[가-힣]", keyword):
        print("⚠️ Yahoo Finance는 한글 종목명 검색을 지원하지 않습니다.")
        print("   영문 회사명(예: 'samsung electronics') 또는 6자리 종목코드로 시도하세요.")
        return

    data = _get_json("/v1/finance/search",
                     {"q": keyword, "quotesCount": 10, "newsCount": 0})
    results = [q for q in data.get("quotes", []) if q.get("symbol")]
    if not results:
        print(f"❌ '{keyword}' 와 일치하는 종목이 없습니다.")
        return

    print("=" * 60)
    print(f"검색 결과: '{keyword}'")
    print("=" * 60)
    for q in results:
        name = q.get("longname") or q.get("shortname") or "-"
        print(f"  {q['symbol']:<12} {name}  [{q.get('exchDisp', '')}/{q.get('typeDisp', '')}]")


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="글로벌 주식 데이터 도구 — 한국/미국/홍콩 등 (Yahoo Finance 기반)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_quote = sub.add_parser("quote", help="실시간 시세")
    p_quote.add_argument("code", help="종목 코드(예: 005930, AAPL, 0700.HK)")

    p_fin = sub.add_parser("financials", help="핵심 재무 데이터(최근 5년)")
    p_fin.add_argument("code", help="종목 코드")

    p_val = sub.add_parser("valuation", help="밸류에이션 지표 + 시총 검산")
    p_val.add_argument("code", help="종목 코드")

    p_search = sub.add_parser("search", help="종목 코드 검색(영문명/티커)")
    p_search.add_argument("keyword", help="영문 회사명 또는 티커")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "quote": lambda: cmd_quote(args.code),
        "financials": lambda: cmd_financials(args.code),
        "valuation": lambda: cmd_valuation(args.code),
        "search": lambda: cmd_search(args.keyword),
    }
    cmds[args.command]()


if __name__ == "__main__":
    main()
