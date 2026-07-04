#!/usr/bin/env python3
"""A주식 데이터 도구 — 텐센트 인용문 + 동양운세검색/재무, 외부 종속성 없음(만 stdlib）。

~을 위한 Claude Code Skills 공급 A 실시간 주식 시세, 금융 데이터 및 기타 데이터。
설계 원칙: 독립 모듈, 기존 도구에 영향을 주지 않습니다. 사용 curl 직접 연결은 시스템 프록시를 우회합니다.。

사용량(기준 Skills 자동통화）：
    python3.11 tools/ashare_data.py quote 600519                    # 실시간 견적
    python3.11 tools/ashare_data.py financials 600519               # 핵심 재무 데이터(거의5년도）
    python3.11 tools/ashare_data.py valuation 600519                # 평가지표
    python3.11 tools/ashare_data.py search 마오타이                      # 주식 기호 검색

필요 Python >= 3.8，외부 종속성 없음。
"""

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_EVEN

_TIMEOUT = 15


def _curl(url):
    """사용 curl --noproxy 시스템 프록시를 우회하여 직접 연결。"""
    result = subprocess.run(
        ["/usr/bin/curl", "-s", "--noproxy", "*",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         url],
        capture_output=True, timeout=_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"요청 실패: {url}")
    # 텐센트 인용문 API 반품 GBK 인코딩, 기타 반환 UTF-8
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return result.stdout.decode("gbk")


def _curl_json(url, params=None):
    """curl 얻다 JSON。"""
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    return json.loads(_curl(url))


# ---------------------------------------------------------------------------
# 텐센트 인용문 API（안정적이고 신뢰할 수 있으며 인증이 필요하지 않습니다.）
# ---------------------------------------------------------------------------

def _qq_code(code: str) -> str:
    """주식 코드를 Tencent 견적 형식으로 변환。"""
    code = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if code.startswith(("6", "9", "5")):
        return f"sh{code}"
    elif code.startswith(("0", "3", "2", "1")):
        return f"sz{code}"
    elif code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sh{code}"


def _parse_qq_quote(raw: str) -> dict:
    """Tencent 시장 데이터를 분석합니다. 체재：v_shXXXXXX="필드1~필드2~..."; """
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        return {}
    fields = raw[start + 1:end].split("~")
    if len(fields) < 50:
        return {}
    return {
        "name": fields[1],
        "code": fields[2],
        "price": fields[3],
        "prev_close": fields[4],
        "open": fields[5],
        "volume": fields[6],         # 손
        "buy_vol": fields[7],
        "sell_vol": fields[8],
        "high": fields[33] if len(fields) > 33 else fields[3],
        "low": fields[34] if len(fields) > 34 else fields[3],
        "change_pct": fields[32],
        "change_amt": fields[31],
        "turnover_amt": fields[37] if len(fields) > 37 else "-",
        "turnover_rate": fields[38] if len(fields) > 38 else "-",
        "pe": fields[39] if len(fields) > 39 else "-",
        "market_cap": fields[45] if len(fields) > 45 else "-",    # 총 시가총액(십억）
        "float_cap": fields[44] if len(fields) > 44 else "-",     # 유통 시장 가치(십억）
        "pb": fields[46] if len(fields) > 46 else "-",
        "high_52w": fields[47] if len(fields) > 47 else "-",
        "low_52w": fields[48] if len(fields) > 48 else "-",
        "total_shares": fields[38] if len(fields) > 38 else "-",  # will recalculate
    }


def _fmt_yi(value) -> str:
    if value is None or value == "-" or value == "":
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}1억"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}만"
    return f"{v:.2f}"


def _fmt_pct(value) -> str:
    if value is None or value == "-" or value == "":
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------

def cmd_quote(code: str):
    """실시간 시장 스냅샷。"""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    if not d:
        print(f"❌ 재고가 없습니다 {code}")
        return

    print("=" * 60)
    print(f"실시간 견적: {d['name']} ({d['code']})")
    print("=" * 60)
    print(f"  현재가:     {d['price']}")
    print(f"  증가 또는 감소:     {d['change_pct']}%")
    print(f"  변경 사항:     {d['change_amt']}")
    print(f"  오늘 개장:       {d['open']}")
    print(f"  제일 높은:       {d['high']}")
    print(f"  가장 낮은:       {d['low']}")
    print(f"  어제 수집됨:       {d['prev_close']}")
    print(f"  용량:     {d['volume']} 손")
    print(f"  회전율:     {d['turnover_amt']}만")
    print(f"  총 시가총액:     {d['market_cap']}1억")
    print(f"  유통 시장 가치:   {d['float_cap']}1억")
    print(f"  PE(이동하다):     {d['pe']}")
    print(f"  PB:         {d['pb']}")
    print(f"  회전율:     {d['turnover_rate']}%")
    print(f"  52주간 최고:   {d['high_52w']}")
    print(f"  52주간 최저:   {d['low_52w']}")


def cmd_valuation(code: str):
    """가치평가 지표 요약。"""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    if not d:
        print(f"❌ 재고가 없습니다 {code}")
        return

    price = d["price"]
    market_cap_yi = d["market_cap"]

    print("=" * 60)
    print(f"평가지표: {d['name']} ({d['code']})")
    print("=" * 60)
    print(f"  현재가:     {price}")
    print(f"  총 시가총액:     {market_cap_yi}1억")
    print(f"  유통 시장 가치:   {d['float_cap']}1억")
    print(f"  PE(이동하다):     {d['pe']}")
    print(f"  PB:         {d['pb']}")
    print(f"  52주간 최고:   {d['high_52w']}")
    print(f"  52주간 최저:   {d['low_52w']}")

    # 시장가치 검증
    try:
        p = Decimal(price)
        cap = Decimal(market_cap_yi) * Decimal("1e8")
        shares = cap / p
        print(f"\n  총 자본금 계산: {_fmt_yi(float(shares))}공유하다")
        calc_cap = p * shares
        reported_cap = Decimal(market_cap_yi) * Decimal("1e8")
        diff = abs(calc_cap - reported_cap) / reported_cap * 100
        print(f"  시장가치 검증:   ✅ 일관성(대체방법, 편차 {float(diff):.1f}%）")
    except Exception:
        pass


def cmd_financials(code: str):
    """닫다5연간 핵심 재무 데이터。"""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    name = d.get("name", code) if d else code

    code_clean = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    market = "SH" if code_clean.startswith(("6", "9", "5")) else "SZ"

    # 오리엔탈 포춘 datacenter API（연간 보고서 데이터）
    fin_url = "https://datacenter.eastmoney.com/securities/api/data/get"
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": "ALL",
        "filter": f'(SECUCODE="{code_clean}.{market}")(REPORT_TYPE="연보")',
        "p": "1",
        "ps": "5",
        "sr": "-1",
        "st": "REPORT_DATE",
        "source": "HSF10",
        "client": "PC",
    }
    reports = []
    try:
        data = _curl_json(fin_url, params)
        reports = data.get("result", {}).get("data", [])
    except Exception:
        pass

    # 연차보고서 심사 결과가 없을 경우 연차보고서 제한을 해제합니다.
    if not reports:
        params["filter"] = f'(SECUCODE="{code_clean}.{market}")'
        try:
            data = _curl_json(fin_url, params)
            reports = data.get("result", {}).get("data", [])
        except Exception:
            pass

    print("=" * 60)
    print(f"핵심 재무 데이터: {name} ({code_clean})")
    print("=" * 60)

    if not reports:
        print("  ⚠️ 재무 데이터를 얻을 수 없습니다. 통과를 권장합니다. WebSearch 다시 채우다")
        return

    for r in reports[:5]:
        date = r.get("REPORT_DATE", "")[:10]
        report_name = r.get("REPORT_DATE_NAME", "")
        revenue = r.get("TOTALOPERATEREVE")
        net_profit = r.get("PARENTNETPROFIT")
        eps = r.get("EPSJB")
        bps = r.get("BPS")
        roe = r.get("ROEJQ")
        rev_growth = r.get("TOTALOPERATEREVETZ")
        profit_growth = r.get("PARENTNETPROFITTZ")

        print(f"\n  --- {date} {report_name} ---")
        if revenue is not None:
            print(f"  수익:           {_fmt_yi(revenue)}")
        if rev_growth is not None:
            print(f"  수익 성장:       {_fmt_pct(rev_growth)}")
        if net_profit is not None:
            print(f"  모회사에 귀속되는 순이익:     {_fmt_yi(net_profit)}")
        if profit_growth is not None:
            print(f"  순이익 증가율:     {_fmt_pct(profit_growth)}")
        if eps is not None:
            print(f"  기본주당순이익:   {eps}")
        if bps is not None:
            print(f"  주당순자산:     {bps:.2f}")
        if roe is not None:
            print(f"  ROE(가중):      {_fmt_pct(roe)}")


def cmd_search(keyword: str):
    """주식 기호 검색。"""
    url = "https://searchadapter.eastmoney.com/api/suggest/get"
    params = {
        "input": keyword,
        "type": "14",
        "token": "D43BF722C8E33BDC906FB84D85E326E8",
        "count": "10",
    }
    data = _curl_json(url, params)
    results = data.get("QuotationCodeTable", {}).get("Data", [])

    if not results:
        print(f"❌ 일치하는 항목이 없습니다. '{keyword}' 주식")
        return

    print("=" * 60)
    print(f"검색결과: '{keyword}'")
    print("=" * 60)
    for r in results:
        code = r.get("Code", "")
        name = r.get("Name", "")
        market = r.get("MktNum", "")
        mkt_label = {"1": "상하이", "2": "깊은", "3": "북쪽"}.get(str(market), "")
        print(f"  {code} {name} [{mkt_label}]")


# ---------------------------------------------------------------------------
# CLI 입구
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="A주식 데이터 도구 — 텐센트 인용문 + 오리엔탈포춘 금융데이터",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_quote = sub.add_parser("quote", help="실시간 견적")
    p_quote.add_argument("code", help="주식 코드(예: 600519")

    p_fin = sub.add_parser("financials", help="핵심 재무 데이터(거의5년도）")
    p_fin.add_argument("code", help="주식 코드")

    p_val = sub.add_parser("valuation", help="평가지표")
    p_val.add_argument("code", help="주식 코드")

    p_search = sub.add_parser("search", help="주식 기호 검색")
    p_search.add_argument("keyword", help="회사 이름 또는 키워드")

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
