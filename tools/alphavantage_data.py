#!/usr/bin/env python3
"""Alpha Vantage 데이터 도구 — 미국 주식 개요·재무제표·일봉·기술지표·뉴스 감성·내부자 거래, 외부 종속성 없음(stdlib만).

무료 키는 하루 25회 제한이 있다(2026년 기준, 변경될 수 있음). 재무제표 원본은 SEC EDGAR(sec_edgar_data.py)가
1차 자료이고, 이 도구는 EDGAR에 없는 데이터(뉴스 감성 점수, 내부자 거래, 기술지표, 개요 지표)와
교차 검증용 부 출처로 쓴다.

시점 통제(--as-of):
  - 개요(overview): 현재 값만 있어 과거 날짜면 보류. 시총·PER·섹터도 '오늘 기준'이기 때문.
  - 재무제표: 회계기간 종료일만 있고 공시일이 없어 과거 날짜면 보류(대안: sec_edgar_data.py --as-of).
  - 내부자 거래: 거래일만 있고 공시(Form 4)일이 없어 과거 날짜면 보류.
  - 일봉·기술지표: as-of 이후 행을 잘라낸다. 뉴스: as-of까지의 기사만 요청한다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)
  tradingagents/dataflows/vendors/alpha_vantage/ 를 stdlib로 이식.

사전 준비:
  무료 키 발급: https://www.alphavantage.co/support/#api-key
      export ALPHA_VANTAGE_API_KEY=발급받은키

사용법:
    python3 tools/alphavantage_data.py overview NVDA
    python3 tools/alphavantage_data.py statement NVDA --kind income --freq annual
    python3 tools/alphavantage_data.py daily NVDA --days 60 --as-of 2025-06-30
    python3 tools/alphavantage_data.py indicator NVDA rsi --days 90
    python3 tools/alphavantage_data.py news NVDA --days 7
    python3 tools/alphavantage_data.py news --macro --days 3          # 거시·시장 전반 뉴스
    python3 tools/alphavantage_data.py insider NVDA

종료 코드: 0 정상 / 3 데이터 없음 / 4 출처 장애·한도 초과 / 5 시점 보류 / 6 키 없음·무효
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import csv
import io
import json
import os
from datetime import datetime, timedelta

from _us_common import (
    NoDataError, NotConfiguredError, UnavailableError, fmt_usd_millions, http_get,
    is_historical, parse_as_of, run, withheld,
)

_BASE = "https://www.alphavantage.co/query"

# 기술지표: 이름 → (AV 함수, 고정 파라미터, CSV 값 열)
_INDICATORS = {
    "close_10_ema": ("EMA", {"time_period": "10", "series_type": "close"}, "EMA"),
    "close_50_sma": ("SMA", {"time_period": "50", "series_type": "close"}, "SMA"),
    "close_200_sma": ("SMA", {"time_period": "200", "series_type": "close"}, "SMA"),
    "rsi": ("RSI", {"time_period": "14", "series_type": "close"}, "RSI"),
    "macd": ("MACD", {"series_type": "close"}, "MACD"),
    "macds": ("MACD", {"series_type": "close"}, "MACD_Signal"),
    "macdh": ("MACD", {"series_type": "close"}, "MACD_Hist"),
    "boll": ("BBANDS", {"time_period": "20", "series_type": "close"}, "Real Middle Band"),
    "boll_ub": ("BBANDS", {"time_period": "20", "series_type": "close"}, "Real Upper Band"),
    "boll_lb": ("BBANDS", {"time_period": "20", "series_type": "close"}, "Real Lower Band"),
    "atr": ("ATR", {"time_period": "14"}, "ATR"),
}

# 재무제표 핵심 계정: (표시명, AV 필드)
_STATEMENT_FIELDS = {
    "income": ("INCOME_STATEMENT", [
        ("매출", "totalRevenue"), ("매출총이익", "grossProfit"), ("영업이익", "operatingIncome"),
        ("순이익", "netIncome"), ("EBITDA", "ebitda"), ("R&D", "researchAndDevelopment"),
    ]),
    "balance": ("BALANCE_SHEET", [
        ("자산총계", "totalAssets"), ("유동자산", "totalCurrentAssets"),
        ("현금성자산", "cashAndCashEquivalentsAtCarryingValue"), ("부채총계", "totalLiabilities"),
        ("장기부채", "longTermDebt"), ("자본총계", "totalShareholderEquity"),
    ]),
    "cashflow": ("CASH_FLOW", [
        ("영업현금흐름", "operatingCashflow"), ("CapEx", "capitalExpenditures"),
        ("투자현금흐름", "cashflowFromInvestment"), ("재무현금흐름", "cashflowFromFinancing"),
        ("배당", "dividendPayout"), ("자사주매입", "paymentsForRepurchaseOfCommonStock"),
    ]),
}

_OVERVIEW_FIELDS = [
    ("이름", "Name"), ("거래소", "Exchange"), ("섹터", "Sector"), ("산업", "Industry"),
    ("시가총액(USD)", "MarketCapitalization"), ("PER", "PERatio"), ("PEG", "PEGRatio"),
    ("PBR", "PriceToBookRatio"), ("EPS(TTM)", "EPS"), ("ROE(TTM)", "ReturnOnEquityTTM"),
    ("영업이익률(TTM)", "OperatingMarginTTM"), ("순이익률", "ProfitMargin"),
    ("배당수익률", "DividendYield"), ("베타", "Beta"), ("52주 고가", "52WeekHigh"),
    ("52주 저가", "52WeekLow"), ("발행주식수", "SharesOutstanding"),
    ("최근 분기", "LatestQuarter"), ("애널리스트 목표가", "AnalystTargetPrice"),
]


def _api_key() -> str:
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not key:
        raise NotConfiguredError(
            "ALPHA_VANTAGE_API_KEY 환경변수가 없습니다. https://www.alphavantage.co/support/#api-key "
            "에서 무료 발급 후 export ALPHA_VANTAGE_API_KEY=키 로 설정하세요.")
    return key


def classify_notice(payload: dict, key: str = "") -> None:
    """AV는 오류를 HTTP 200 + JSON 안내문으로 돌려준다. 성격별로 예외를 나눈다.

    한도 안내문에도 'API key'라는 말이 들어가므로("your API key ... 25 requests per day") 한도를 먼저 검사한다.
    """
    notice = payload.get("Information") or payload.get("Note")
    if notice:
        notice = notice.replace(key, "***") if key else notice
        low = notice.lower()
        if any(m in low for m in ("rate limit", "requests per day", "call frequency", "premium")):
            raise UnavailableError(f"Alpha Vantage 한도 초과 또는 유료 전용: {notice}")
        if "api key" in low or "apikey" in low:
            raise NotConfiguredError(f"Alpha Vantage API 키가 무효합니다: {notice}")
    # 알 수 없는 종목과 잘못된 호출이 똑같이 "Error Message"로 와서, 종목에 대해서는 아무것도 말해주지 않는다.
    rejection = payload.get("Error Message")
    if rejection:
        raise UnavailableError(f"Alpha Vantage 요청 거부: {rejection.replace(key, '***') if key else rejection}")


def _request(function: str, params: dict):
    """JSON이면 dict, CSV면 문자열을 돌려준다."""
    key = _api_key()
    status, body = http_get(_BASE, dict(params, function=function, apikey=key), secret=key)
    if not 200 <= status < 300:
        raise UnavailableError(f"Alpha Vantage HTTP {status}")
    try:
        payload = json.loads(body)
    except ValueError:
        return body  # CSV 데이터
    if isinstance(payload, dict):
        classify_notice(payload, key)
    return payload


def _num(value):
    """AV는 숫자를 문자열로, 결측을 "None"으로 준다."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def filter_csv(text: str, start: str, end: str, date_col: str) -> list:
    """CSV 행 중 start~end(포함) 날짜만. 이 절단이 과거 시점 분석에서 미래 가격을 막는 유일한 장치라
    파싱 실패를 삼키지 않는다(실패 시 잘리지 않은 데이터가 나가면 미래 정보 유출)."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and date_col not in rows[0]:
        raise UnavailableError(f"예상한 날짜 열 '{date_col}' 이 응답에 없습니다: {list(rows[0])}")
    return [r for r in rows if start <= r[date_col][:10] <= end]


def cmd_overview(ticker: str, as_of: str):
    if is_historical(as_of):
        withheld("Alpha Vantage", "기업 개요", as_of,
                 "개요는 현재 값만 있습니다. 시총·PER·52주 범위는 오늘 주가 기준이고, 섹터·사명도 오늘 기준입니다.",
                 f"재무는 python3 tools/sec_edgar_data.py financials {ticker} --as-of {as_of}")
    data = _request("OVERVIEW", {"symbol": ticker})
    if not data or not isinstance(data, dict) or not data.get("Symbol"):
        raise NoDataError(f"{ticker.upper()} 의 개요 데이터가 없습니다.")
    print("=" * 64)
    print(f"Alpha Vantage 개요: {data.get('Name')} ({data.get('Symbol')}) — 현재 시점 값")
    print("=" * 64)
    for label, field in _OVERVIEW_FIELDS:
        print(f"  {label:<16} {data.get(field, '-')}")
    print("\n  출처: Alpha Vantage OVERVIEW. 시총은 반드시 주가×주식수로 수동 검산(CLAUDE.md).")


def cmd_statement(ticker: str, kind: str, freq: str, as_of: str, limit: int):
    if is_historical(as_of):
        withheld("Alpha Vantage", "재무제표", as_of,
                 "회계기간 종료일만 있고 공시일이 없어, 그 날짜에 공개돼 있었는지 알 수 없습니다.",
                 f"python3 tools/sec_edgar_data.py financials {ticker} --as-of {as_of}")
    function, fields = _STATEMENT_FIELDS[kind]
    data = _request(function, {"symbol": ticker})
    reports = (data or {}).get("annualReports" if freq == "annual" else "quarterlyReports") or []
    if not reports:
        raise NoDataError(f"{ticker.upper()} 의 {function} 데이터가 없습니다.")
    reports = sorted(reports, key=lambda r: r.get("fiscalDateEnding", ""))[-limit:]
    print("=" * 72)
    print(f"Alpha Vantage {function}: {ticker.upper()} ({'연간' if freq == 'annual' else '분기'}) "
          f"— 단위 백만 {reports[-1].get('reportedCurrency', 'USD')}")
    print("=" * 72)
    print("  " + " | ".join(["회계기간 종료"] + [lb for lb, _ in fields]))
    for r in reports:
        cells = [fmt_usd_millions(_num(r.get(f))) for _, f in fields]
        print("  " + " | ".join([r.get("fiscalDateEnding", "?")] + cells))
    print("\n  출처: Alpha Vantage(부 출처). 원본은 SEC EDGAR(sec_edgar_data.py)와 대조.")


def cmd_daily(ticker: str, days: int, as_of: str):
    start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    # compact는 최근 100거래일만. 시작일이 그보다 이전이면 full.
    full = (datetime.now() - datetime.strptime(start, "%Y-%m-%d")).days >= 100
    text = _request("TIME_SERIES_DAILY", {"symbol": ticker, "datatype": "csv",
                                          "outputsize": "full" if full else "compact"})
    if not isinstance(text, str):
        raise UnavailableError("일봉 응답이 CSV가 아닙니다.")
    rows = sorted(filter_csv(text, start, as_of, "timestamp"), key=lambda r: r["timestamp"])
    if not rows:
        raise NoDataError(f"{ticker.upper()} 의 {start}~{as_of} 일봉이 없습니다.")
    print("=" * 64)
    print(f"Alpha Vantage 일봉: {ticker.upper()} {start} ~ {as_of} ({len(rows)}거래일, 수정주가 아님)")
    print("=" * 64)
    print("  날짜        |    시가 |    고가 |    저가 |    종가 |       거래량")
    for r in rows:
        print(f"  {r['timestamp']}  | {float(r['open']):>7.2f} | {float(r['high']):>7.2f} | "
              f"{float(r['low']):>7.2f} | {float(r['close']):>7.2f} | {int(float(r['volume'])):>12,}")


def cmd_indicator(ticker: str, name: str, days: int, as_of: str):
    if name not in _INDICATORS:
        raise NoDataError(f"지원하지 않는 지표: {name}. 지원: {', '.join(_INDICATORS)}")
    function, fixed, column = _INDICATORS[name]
    text = _request(function, dict(fixed, symbol=ticker, interval="daily", datatype="csv"))
    if not isinstance(text, str):
        raise UnavailableError(f"{function} 응답이 CSV가 아닙니다.")
    start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = sorted(filter_csv(text, start, as_of, "time"), key=lambda r: r["time"])
    if rows and column not in rows[0]:
        raise UnavailableError(f"'{column}' 열이 없습니다: {list(rows[0])}")
    if not rows:
        raise NoDataError(f"{ticker.upper()} {name} 의 {start}~{as_of} 값이 없습니다.")
    print(f"Alpha Vantage {name} ({function}): {ticker.upper()} {start} ~ {as_of}")
    for r in rows:
        print(f"  {r['time']}: {r[column]}")


def cmd_news(ticker: str, macro: bool, days: int, as_of: str, limit: int):
    end = datetime.strptime(as_of, "%Y-%m-%d")
    params = {
        "time_from": (end - timedelta(days=days)).strftime("%Y%m%dT0000"),
        # 날짜만 주면 자정(그날 시작)이 되어 기준일 기사가 빠지므로 23:59까지.
        "time_to": end.strftime("%Y%m%dT2359"),
        "limit": str(limit),
    }
    if macro:
        params["topics"] = "financial_markets,economy_macro,economy_monetary"
    else:
        params["tickers"] = ticker
    data = _request("NEWS_SENTIMENT", params)
    feed = (data or {}).get("feed") or []
    if not feed:
        raise NoDataError(f"{'거시' if macro else ticker.upper()} 뉴스가 해당 기간에 없습니다.")
    print("=" * 72)
    print(f"Alpha Vantage 뉴스·감성: {'거시/시장 전반' if macro else ticker.upper()} "
          f"(최근 {days}일, {as_of} 까지, {len(feed)}건)")
    print("  감성 점수: -1(약세) ~ +1(강세). AV 자체 모델 산출값이며 사실이 아니라 참고 신호.")
    print("=" * 72)
    for item in feed[:limit]:
        t = item.get("time_published", "")
        when = f"{t[:4]}-{t[4:6]}-{t[6:8]} {t[9:11]}:{t[11:13]}" if len(t) >= 13 else t
        tick = ""
        if not macro:
            mine = [s for s in item.get("ticker_sentiment", []) if s.get("ticker", "").upper() == ticker.upper()]
            if mine:
                tick = (f" | 종목 감성 {mine[0].get('ticker_sentiment_label')} "
                        f"{mine[0].get('ticker_sentiment_score')} (관련도 {mine[0].get('relevance_score')})")
        print(f"  [{when}] {item.get('source', '')}: {item.get('title', '')}")
        print(f"      전체 감성 {item.get('overall_sentiment_label')} {item.get('overall_sentiment_score')}{tick}")
        print(f"      {item.get('url', '')}")


def cmd_insider(ticker: str, as_of: str, limit: int):
    if is_historical(as_of):
        withheld("Alpha Vantage", "내부자 거래", as_of,
                 "거래일만 있고 공시(Form 4, 거래 후 최대 2영업일)일이 없어 그날 공개됐는지 알 수 없습니다.",
                 f"python3 tools/sec_edgar_data.py filings {ticker} --forms 4 --as-of {as_of}")
    data = _request("INSIDER_TRANSACTIONS", {"symbol": ticker})
    rows = (data or {}).get("data") or []
    if not rows:
        raise NoDataError(f"{ticker.upper()} 의 내부자 거래 데이터가 없습니다.")
    rows = sorted(rows, key=lambda r: r.get("transaction_date", ""), reverse=True)[:limit]
    print("=" * 72)
    print(f"Alpha Vantage 내부자 거래: {ticker.upper()} (최근 {len(rows)}건, A=취득 D=처분)")
    print("=" * 72)
    for r in rows:
        print(f"  [{r.get('transaction_date')}] {r.get('acquisition_or_disposal')} "
              f"{r.get('shares')}주 @ {r.get('share_price')} — {r.get('executive')} "
              f"({r.get('executive_title')}), {r.get('security_type')}")


def main():
    p = argparse.ArgumentParser(description="Alpha Vantage 미국 주식 데이터 도구.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, help_text, ticker=True):
        sp = sub.add_parser(name, help=help_text)
        if ticker:
            sp.add_argument("ticker")
        sp.add_argument("--as-of", default="", help="분석 기준일(YYYY-MM-DD, 기본 오늘)")
        return sp

    add("overview", "기업 개요·밸류에이션 지표(현재 시점)")
    ps = add("statement", "재무제표 핵심 계정")
    ps.add_argument("--kind", default="income", choices=list(_STATEMENT_FIELDS))
    ps.add_argument("--freq", default="annual", choices=["annual", "quarterly"])
    ps.add_argument("--limit", type=int, default=5)
    pd = add("daily", "일봉 OHLCV")
    pd.add_argument("--days", type=int, default=60)
    pi = add("indicator", "기술지표")
    pi.add_argument("name", choices=list(_INDICATORS))
    pi.add_argument("--days", type=int, default=90)
    pn = sub.add_parser("news", help="뉴스·감성 점수")
    pn.add_argument("ticker", nargs="?", default="")
    pn.add_argument("--macro", action="store_true", help="종목 대신 거시·시장 전반 뉴스")
    pn.add_argument("--days", type=int, default=7)
    pn.add_argument("--limit", type=int, default=15)
    pn.add_argument("--as-of", default="")
    pin = add("insider", "내부자 거래")
    pin.add_argument("--limit", type=int, default=20)

    args = p.parse_args()
    as_of = parse_as_of(args.as_of)
    if args.cmd == "overview":
        cmd_overview(args.ticker, as_of)
    elif args.cmd == "statement":
        cmd_statement(args.ticker, args.kind, args.freq, as_of, args.limit)
    elif args.cmd == "daily":
        cmd_daily(args.ticker, args.days, as_of)
    elif args.cmd == "indicator":
        cmd_indicator(args.ticker, args.name, args.days, as_of)
    elif args.cmd == "news":
        if not args.macro and not args.ticker:
            p.error("news 는 ticker 또는 --macro 가 필요합니다.")
        cmd_news(args.ticker, args.macro, args.days, as_of, args.limit)
    elif args.cmd == "insider":
        cmd_insider(args.ticker, as_of, args.limit)


if __name__ == "__main__":
    run(main)
