#!/usr/bin/env python3
"""팩트시트(확정 수치표) — 리서치 전에 핵심 수치를 도구로 한 번에 뽑아 '기준값'으로 고정한다. stdlib만.

LLM이 숫자를 기억이나 검색 조각에서 가져오면 오류가 섞인다. 리서치 시작 시 이 표를 만들어 모든
Agent에 같은 표를 주고, "정확한 수치는 이 표가 기준, 다른 출처와 다르면 불일치로 표기하고 임의로
맞춘 숫자를 만들지 말 것"을 지시한다. report_audit.py 가 출고 직전에 15%를 사후 표본 검사한다면,
이 표는 수치 오류를 사전에 막는다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)의
  get_verified_market_snapshot(결정론적 검증 스냅샷, LLM 미개입)을 재무 수치까지 넓혀 적용.

내용:
  - 시세·밸류에이션: 현재가, 52주 범위, 발행주식수, 시가총액(+ 주가×주식수 검산), PER/PBR(TTM)
  - 연간 재무(최근 N년): 매출, 영업이익, 지배순이익, 희석EPS, 자본, 영업CF, CapEx, FCF와
    같은 통화끼리만 계산한 영업이익률·순이익률·ROE·영업CF/순이익
  - 한국 우선주 처리(DART_API_KEY 있을 때): DART 주식 총수로 보통주·우선주·자기주식을 나누고,
    보통+우선 유통주식 기준 시총·EPS·BPS·PER·PBR을 다시 계산한다(분자는 TTM 순이익·최근 분기 자본, 없으면
    직전 회계연도). Yahoo 발행주식수는 우선주·자기주식 처리가 일정하지 않아 참고로만 쓴다.
    우선주가 여러 종류면(현대차 우·2우B·3우B 등) DART가 합산값만 줘서 우선주 시총은 계산하지 않는다.
  - 1차 출처 교차 검증: 한국 DART(DART_API_KEY 있을 때)·네이버 시총·BPS, 미국 SEC EDGAR
    편차 ≤1% ✅ / 1~5% ⚠️ / >5% ❌ (financial-data 규범)
  - 통화: 주가 통화와 재무 통화를 따로 표시. 다르면(텐센트 HKD/CNY, PDD USD/CNY 등) 경고하고
    두 통화를 섞는 계산(주가÷EPS 등)은 하지 않는다. PER/PBR은 Yahoo가 환산한 값을 출처와 함께 쓴다.

참고: DART 교차 검증은 첫 실행 때 DART 기업코드 목록(약 3.5MB)을 내려받아 tools/.cache/ 에 저장하므로 수 분 걸릴 수 있다.

한계: 현재 시점 스냅샷이다. 과거 시점 분석에는 쓰지 말고 dart_data.py / sec_edgar_data.py 의 --as-of 를 쓴다.

사용법:
    python3 tools/fact_sheet.py 005930            # 마크다운 표(보고서 부록·Agent 프롬프트용)
    python3 tools/fact_sheet.py AAPL --years 5
    python3 tools/fact_sheet.py 0700 --json       # 기계가 읽는 JSON

종료 코드: 0 정상(일부 항목 없음은 표에 '데이터 없음'으로 표기) / 3 종목 없음 / 4 시세 출처 장애
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import json
import os
import re
import time
from datetime import date, datetime, timezone

from _us_common import NoDataError, UnavailableError, run

_ANNUAL = {
    "매출": "annualTotalRevenue",
    "영업이익": "annualOperatingIncome",
    "지배순이익": "annualNetIncomeCommonStockholders",
    "희석EPS": "annualDilutedEPS",
    "자본": "annualStockholdersEquity",
    "영업CF": "annualOperatingCashFlow",
    "CapEx": "annualCapitalExpenditure",
    "FCF": "annualFreeCashFlow",
}
_SNAPSHOT = ["trailingMarketCap", "trailingPeRatio", "trailingPbRatio", "quarterlyShareIssued",
             "trailingNetIncomeCommonStockholders", "quarterlyStockholdersEquity"]


def grade(a, b):
    """두 값의 편차(%)와 판정. 기준은 a(1차 출처)."""
    if a in (None, 0) or b is None:
        return None, "비교 불가"
    diff = abs(a - b) / abs(a) * 100
    return diff, "✅" if diff <= 1 else ("⚠️" if diff <= 5 else "❌")


def _fact(value, source, as_of, unit=""):
    return {"value": value, "unit": unit, "source": source, "date": as_of}


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

def yahoo_series(symbol: str, types: list, years: int) -> dict:
    """fundamentals-timeseries → {타입: [(날짜, 값, 통화)]} (날짜 오름차순). 통화 코드를 버리지 않는다."""
    from global_stock_data import _get_json
    now = int(time.time())
    data = _get_json(f"/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}",
                     {"type": ",".join(types), "period1": now - (years + 1) * 366 * 86400, "period2": now})
    out = {}
    for r in (data.get("timeseries") or {}).get("result") or []:
        t = ((r.get("meta") or {}).get("type") or [None])[0]
        rows = [(v["asOfDate"], v["reportedValue"]["raw"], v.get("currencyCode", ""))
                for v in (r.get(t) or [])
                if v and v.get("asOfDate") and (v.get("reportedValue") or {}).get("raw") is not None]
        if t:
            out[t] = sorted(rows)
    return out


def collect(code: str, years: int = 3) -> dict:
    from global_stock_data import _resolve
    try:
        symbol, meta = _resolve(code)
    except Exception as e:  # noqa: BLE001 — 네트워크 계열 실패는 출처 장애
        raise UnavailableError(f"Yahoo 시세 조회 실패: {e}")
    if not symbol:
        raise NoDataError(f"{code} 를 Yahoo Finance에서 찾지 못했습니다.")
    try:
        ts = yahoo_series(symbol, list(_ANNUAL.values()) + _SNAPSHOT, years)
    except Exception as e:  # noqa: BLE001
        raise UnavailableError(f"Yahoo 재무 시계열 조회 실패: {e}")

    price_cur = meta.get("currency", "")
    price_ts = meta.get("regularMarketTime")
    price_date = (datetime.fromtimestamp(price_ts + meta.get("gmtoffset", 0), tz=timezone.utc).strftime("%Y-%m-%d")
                  if price_ts else "")
    last = {t: (ts.get(t) or [None])[-1] for t in _SNAPSHOT}
    fin_cur = next((rows[-1][2] for t in _ANNUAL.values() if (rows := ts.get(t))), "")

    sheet = {
        "name": meta.get("longName") or meta.get("shortName") or code,
        "symbol": symbol, "exchange": meta.get("fullExchangeName", ""),
        "price_currency": price_cur, "financial_currency": fin_cur,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "snapshot": {}, "annual": [], "checks": [], "warnings": [],
        # 주당 지표 재계산용 최근값: (날짜, 값, 통화) 또는 None
        "basis": {"TTM 지배순이익": last["trailingNetIncomeCommonStockholders"],
                  "최근 분기 자본": last["quarterlyStockholdersEquity"]},
    }
    snap = sheet["snapshot"]

    def positive(v):
        # Yahoo가 결측을 0으로 주는 경우가 있다(예: 52주 최저 0원). 0 이하 가격은 데이터 없음으로 본다.
        return v if isinstance(v, (int, float)) and v > 0 else None

    snap["현재가"] = _fact(positive(meta.get("regularMarketPrice")), "Yahoo chart", price_date, price_cur)
    snap["52주 최고"] = _fact(positive(meta.get("fiftyTwoWeekHigh")), "Yahoo chart", price_date, price_cur)
    snap["52주 최저"] = _fact(positive(meta.get("fiftyTwoWeekLow")), "Yahoo chart", price_date, price_cur)
    for label, t, unit in (("발행주식수", "quarterlyShareIssued", "주"), ("시가총액", "trailingMarketCap", price_cur),
                           ("PER(TTM)", "trailingPeRatio", "배"), ("PBR", "trailingPbRatio", "배")):
        row = last[t]
        snap[label] = _fact(row[1] if row else None, "Yahoo timeseries", row[0] if row else "", unit)

    if fin_cur and price_cur and fin_cur != price_cur:
        sheet["warnings"].append(
            f"주가 통화({price_cur})와 재무 통화({fin_cur})가 다르다. 주가와 재무 수치를 섞어 계산할 때는 "
            f"같은 시점 환율로 환산하고 환율·기준일을 명시할 것(이 표는 섞어 계산하지 않는다).")

    # 시가총액 검산: 주가 × 발행주식수 (같은 주가 통화)
    price, shares, mcap = (snap["현재가"]["value"], snap["발행주식수"]["value"], snap["시가총액"]["value"])
    if price and shares and mcap:
        diff, mark = grade(mcap, price * shares)
        sheet["checks"].append({"항목": "시가총액 검산(주가×주식수)", "기간": price_date,
                                "기준": mcap, "기준출처": "Yahoo 시총", "비교": price * shares,
                                "비교출처": "주가×발행주식수", "편차": diff, "판정": mark, "통화": price_cur})

    # 연간 재무 표 + 같은 통화끼리만 계산한 비율
    periods = sorted({d for t in _ANNUAL.values() for d, _, _ in ts.get(t, [])})[-years:]
    for p in periods:
        row = {"기간": p}
        for label, t in _ANNUAL.items():
            hit = [v for d, v, c in ts.get(t, []) if d == p]
            row[label] = hit[0] if hit else None
        rev, op, ni, eq, ocf = (row["매출"], row["영업이익"], row["지배순이익"], row["자본"], row["영업CF"])
        row["영업이익률"] = op / rev * 100 if rev and op is not None else None
        row["순이익률"] = ni / rev * 100 if rev and ni is not None else None
        row["ROE"] = ni / eq * 100 if eq and ni is not None else None
        row["영업CF/순이익"] = ocf / ni if ni and ocf is not None else None
        sheet["annual"].append(row)

    latest = sheet["annual"][-1] if sheet["annual"] else None
    if symbol.endswith((".KS", ".KQ")):
        _check_korea(sheet, symbol, latest, price_date)
    elif "." not in symbol:
        _check_us(sheet, symbol, latest)
    else:
        sheet["warnings"].append("이 시장은 자동 1차 출처 교차 검증이 없다. financial-data 규범대로 "
                                 "연차보고서(HKEX/cninfo 등)와 수동 대조할 것.")
    return sheet


def _check_korea(sheet: dict, symbol: str, latest: dict, price_date: str):
    from global_stock_data import _naver_market_cap
    code6 = symbol.split(".")[0]
    mcap = sheet["snapshot"]["시가총액"]["value"]
    naver = _naver_market_cap(code6)
    if naver and mcap:
        diff, mark = grade(naver, mcap)
        sheet["checks"].append({"항목": "시가총액", "기간": price_date, "기준": naver, "기준출처": "네이버(보통주)",
                                "비교": mcap, "비교출처": "Yahoo", "편차": diff, "판정": mark, "통화": "KRW"})
        if mark != "✅":
            sheet["warnings"].append("Yahoo 시총·주식수는 우선주·자기주식 처리 기준이 불분명하다. 한국 종목의 시총·주당 "
                                     "지표는 네이버(보통주)와 DART 주식수 기준 값을 쓸 것.")
    if not os.environ.get("DART_API_KEY"):
        sheet["warnings"].append("DART_API_KEY 가 없어 DART(1차 출처) 교차 검증과 우선주 포함 주식수 계산을 하지 못했다. "
                                 "python3 tools/dart_data.py financials " + code6 + " 로 확인할 것.")
        return
    import dart_data
    try:
        corp_code, _ = dart_data._resolve(code6)
    except (RuntimeError, ConnectionError, SystemExit) as e:
        sheet["warnings"].append(f"DART 조회 실패({e}) — 교차 검증 생략.")
        return
    if not corp_code:
        sheet["warnings"].append(f"DART에서 {code6} 의 기업코드를 찾지 못했다 — 교차 검증 생략.")
        return
    _korea_shares(sheet, code6, corp_code, latest, price_date, naver)
    if not latest:
        return
    try:
        items = dart_data._fetch_financials(corp_code, int(latest["기간"][:4]), "11011", "CFS")
    except (RuntimeError, ConnectionError, SystemExit) as e:
        sheet["warnings"].append(f"DART 조회 실패({e}) — 교차 검증 생략.")
        return
    if not items:
        sheet["warnings"].append(f"DART에 {latest['기간'][:4]} 사업보고서 연결 재무가 없다 — 교차 검증 생략.")
        return
    acc = dart_data._extract_accounts(items, "CFS")
    for label, dart_label in (("매출", "매출액"), ("영업이익", "영업이익"), ("지배순이익", "지배주주순이익"),
                              ("영업CF", "영업활동현금흐름")):
        primary = (acc.get(dart_label) or {}).get("thstrm")
        diff, mark = grade(primary, latest.get(label))
        sheet["checks"].append({"항목": label, "기간": latest["기간"], "기준": primary, "기준출처": "DART(연결)",
                                "비교": latest.get(label), "비교출처": "Yahoo", "편차": diff, "판정": mark,
                                "통화": "KRW"})


def _preferred_price(code6: str):
    """첫 우선주(종목코드 끝자리 5·7·9 관례) 시세 → (심볼, 가격, 메시지). 한 종류일 때만 가격을 준다.

    DART는 우선주를 종류와 무관하게 합산하므로, 종류가 둘 이상이면 종류별 주식수를 알 수 없어 시총을 계산하지 않는다.
    """
    from global_stock_data import _resolve
    if not code6.endswith("0"):
        return None, None, f"보통주 코드({code6})가 0으로 끝나지 않아 우선주 종목코드를 추정하지 않았다."
    found = []
    for suffix in "579":
        try:
            sym, m = _resolve(code6[:5] + suffix)
        except Exception:  # noqa: BLE001 — 후보 하나의 조회 실패는 '없음'으로 본다
            continue
        price = (m or {}).get("regularMarketPrice")
        if sym and isinstance(price, (int, float)) and price > 0:
            found.append((sym, float(price)))
    if len(found) == 1:
        return found[0][0], found[0][1], ""
    if not found:
        return None, None, "우선주 시세를 찾지 못했다(종목코드 끝자리 5·7·9 확인)."
    return None, None, (f"우선주가 {len(found)}종류({', '.join(s for s, _ in found)})인데 DART 주식수는 합산값뿐이라 "
                        "우선주 시총을 계산하지 않았다. 종류별 주식수는 사업보고서 '주식의 총수'로 확인할 것.")


def _korea_shares(sheet: dict, code6: str, corp_code: str, latest: dict, price_date: str, naver):
    """DART 주식 총수로 보통주·우선주를 나눠 시총과 주당 지표를 다시 계산한다.

    Yahoo 발행주식수는 우선주·자기주식 처리가 일정하지 않다(삼성전자: 보통주와도 보통+우선과도 다름).
    주당 지표의 분모는 보통+우선 유통주식수(자기주식 제외)로 한다.
    """
    import dart_data
    try:
        sc = dart_data.share_counts(corp_code)
    except (RuntimeError, ConnectionError, SystemExit) as e:
        sheet["warnings"].append(f"DART 주식 총수 조회 실패({e}) — 우선주 포함 계산 생략.")
        return
    if not sc:
        sheet["warnings"].append("DART에서 최근 정기보고서의 주식 총수를 얻지 못했다 — 우선주 포함 계산 생략.")
        return
    snap, pc = sheet["snapshot"], sheet["price_currency"]
    src, as_of = f"DART {sc['보고서']}", sc["기준일"]
    common, pref = sc["보통주"], sc["우선주"]
    total_out = common["유통"] + pref["유통"]
    snap["보통주 발행주식수"] = _fact(common["발행"], src, as_of, "주")
    snap["우선주 발행주식수"] = _fact(pref["발행"], src, as_of, "주")
    snap["자기주식(보통+우선)"] = _fact(common["자기주식"] + pref["자기주식"], src, as_of, "주")
    snap["유통주식수(보통+우선)"] = _fact(total_out, src, as_of, "주")

    yahoo_shares = snap["발행주식수"]["value"]
    if yahoo_shares:
        bases = (common["발행"], common["유통"], common["발행"] + pref["발행"], total_out)
        if all((grade(b, yahoo_shares)[0] or 0) > 0.1 for b in bases if b):
            sheet["warnings"].append(
                f"Yahoo 발행주식수({yahoo_shares:,.0f}주)가 DART 보통주({common['발행']:,.0f}주)·"
                f"보통+우선({common['발행'] + pref['발행']:,.0f}주) 어느 쪽과도 맞지 않는다. 주당 지표는 DART 기준 값을 쓸 것.")

    price = snap["현재가"]["value"]
    if price and naver:
        diff, mark = grade(naver, price * common["발행"])
        sheet["checks"].append({"항목": "시가총액(보통주) 검산", "기간": price_date, "기준": naver,
                                "기준출처": "네이버(보통주)", "비교": price * common["발행"],
                                "비교출처": "주가×DART 보통주 발행주식수", "편차": diff, "판정": mark, "통화": "KRW"})

    equity_value = None
    if price and pref["유통"] > 0:
        pref_sym, pref_price, msg = _preferred_price(code6)
        if pref_price:
            snap["우선주 현재가"] = _fact(pref_price, f"Yahoo chart {pref_sym}", price_date, pc)
            equity_value = price * common["유통"] + pref_price * pref["유통"]
        else:
            sheet["warnings"].append(msg)
    elif price:
        equity_value = price * common["유통"]
    if equity_value:
        snap["시가총액(보통+우선, 유통주식)"] = _fact(equity_value, "주가×DART 유통주식수", price_date, pc)

    if sheet["financial_currency"] != pc or not total_out:
        return
    # 분자는 최근값(TTM 순이익, 최근 분기 자본)을 우선 쓰고, 없으면 직전 회계연도 값을 쓴다.
    fy = latest["기간"][:4] if latest else ""
    ni_row = sheet["basis"].get("TTM 지배순이익") or (latest and (latest["기간"], latest.get("지배순이익"), pc))
    eq_row = sheet["basis"].get("최근 분기 자본") or (latest and (latest["기간"], latest.get("자본"), pc))
    ni_tag = ("TTM" if sheet["basis"].get("TTM 지배순이익") else f"FY{fy}") if ni_row else ""
    eq_tag = ("최근 분기" if sheet["basis"].get("최근 분기 자본") else f"FY{fy}") if eq_row else ""
    ni = ni_row[1] if ni_row else None
    eq = eq_row[1] if eq_row else None
    snap["EPS(보통+우선 유통주식)"] = _fact(ni / total_out if ni else None,
                                         f"{ni_tag} 지배순이익({ni_row[0] if ni_row else '-'}) ÷ DART 유통주식수", as_of, pc)
    bps = eq / total_out if eq else None
    snap["BPS(보통+우선 유통주식)"] = _fact(bps, f"{eq_tag} 지배주주 자본({eq_row[0] if eq_row else '-'}) ÷ DART 유통주식수",
                                         as_of, pc)
    if equity_value:
        snap["PER(우선주 포함)"] = _fact(equity_value / ni if ni and ni > 0 else None,
                                       f"보통+우선 시총 ÷ {ni_tag} 지배순이익", price_date, "배")
        snap["PBR(우선주 포함)"] = _fact(equity_value / eq if eq and eq > 0 else None,
                                       f"보통+우선 시총 ÷ {eq_tag} 지배주주 자본", price_date, "배")
    naver_bps = _naver_number(code6, "BPS")
    if bps and naver_bps:
        diff, mark = grade(naver_bps, bps)
        sheet["checks"].append({"항목": "BPS(보통+우선)", "기간": eq_row[0], "기준": naver_bps, "기준출처": "네이버",
                                "비교": bps, "비교출처": "자본÷DART 유통주식수", "편차": diff, "판정": mark,
                                "통화": "KRW"})


def _naver_number(code6: str, key: str):
    """네이버 모바일 integration API의 숫자 항목(예: BPS '86,052원'). 실패 시 None."""
    from global_stock_data import _NAVER_API, _naver_json
    try:
        for item in _naver_json(f"{_NAVER_API}/stock/{code6}/integration").get("totalInfos", []):
            if item.get("key") == key:
                digits = re.sub(r"[^0-9.\-]", "", item.get("value", ""))
                return float(digits) if digits else None
    except Exception:  # noqa: BLE001 — 부 출처 실패는 비교 생략
        pass
    return None


def _check_us(sheet: dict, symbol: str, latest: dict):
    if not latest:
        return
    import sec_edgar_data as sec
    try:
        _, _, us_gaap = sec._load_us_gaap(symbol)
    except (NoDataError, UnavailableError) as e:
        sheet["warnings"].append(f"SEC EDGAR 조회 실패({e}) — 교차 검증 생략.")
        return
    today = date.today().strftime("%Y-%m-%d")
    end = datetime.strptime(latest["기간"], "%Y-%m-%d")
    pairs = (("income", "매출", "매출"), ("income", "영업이익", "영업이익"), ("income", "순이익", "지배순이익"),
             ("cashflow", "영업현금흐름", "영업CF"), ("balance", "자본총계", "자본"))
    tables = {k: dict(sec.statement_table(us_gaap, k, "annual", today)[0]) for k in ("income", "cashflow", "balance")}
    for kind, sec_label, label in pairs:
        # Yahoo 회계연도 종료일과 SEC 기간 종료일은 며칠 어긋날 수 있다(52/53주 회계연도).
        match = [v for p, v in tables[kind].items()
                 if abs((datetime.strptime(p[:10], "%Y-%m-%d") - end).days) <= 10]
        primary = match[0].get(sec_label) if match else None
        diff, mark = grade(primary, latest.get(label))
        sheet["checks"].append({"항목": label, "기간": latest["기간"], "기준": primary, "기준출처": "SEC EDGAR",
                                "비교": latest.get(label), "비교출처": "Yahoo", "편차": diff, "판정": mark,
                                "통화": sheet["financial_currency"]})


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

def _big(v, cur):
    from global_stock_data import _fmt_big
    return "데이터 없음" if v is None else _fmt_big(v, cur)


def _num(v, digits=2, suffix=""):
    return "데이터 없음" if v is None else f"{v:,.{digits}f}{suffix}"


def render(sheet: dict) -> str:
    pc, fc = sheet["price_currency"], sheet["financial_currency"]
    s = sheet["snapshot"]
    lines = [
        f"# 팩트시트: {sheet['name']} ({sheet['symbol']})",
        "",
        f"생성: {sheet['generated']} — **현재 시점 스냅샷**(과거 시점 분석에는 쓰지 말 것) · "
        f"주가 통화 {pc or '?'} · 재무 통화 {fc or '?'}",
        "",
        "## 시세·밸류에이션",
        "| 항목 | 값 | 출처 | 기준일 |",
        "|---|---|---|---|",
    ]
    for label, f in s.items():
        v = f["value"]
        if label.startswith("시가총액"):
            shown = _big(v, pc)
        elif f["unit"] == "주":
            shown = _num(v, 0, "주")
        elif f["unit"] == "배":
            shown = _num(v, 2, "배")
        else:
            shown = _num(v, 2, f" {pc}")
        lines.append(f"| {label} | {shown} | {f['source']} | {f['date'] or '-'} |")

    lines += ["", f"## 연간 재무 (재무 통화 {fc}, 출처 Yahoo timeseries)",
              "| 회계연도 | 매출 | 영업이익 | 지배순이익 | 희석EPS | 자본 | 영업CF | CapEx | FCF | 영업이익률 | 순이익률 | ROE | 영업CF/순이익 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sheet["annual"]:
        lines.append("| " + " | ".join([
            r["기간"], _big(r["매출"], fc), _big(r["영업이익"], fc), _big(r["지배순이익"], fc), _num(r["희석EPS"], 2, f" {fc}"),
            _big(r["자본"], fc), _big(r["영업CF"], fc), _big(r["CapEx"], fc), _big(r["FCF"], fc),
            _num(r["영업이익률"], 1, "%"), _num(r["순이익률"], 1, "%"), _num(r["ROE"], 1, "%"),
            _num(r["영업CF/순이익"], 2)]) + " |")
    if not sheet["annual"]:
        lines.append("| 데이터 없음 | | | | | | | | | | | | |")

    lines += ["", "## 교차 검증 (기준 = 1차 출처, ≤1% ✅ / 1~5% ⚠️ / >5% ❌)",
              "| 항목 | 기간 | 기준(출처) | 비교(출처) | 편차 | 판정 |", "|---|---|---|---|---|---|"]
    for c in sheet["checks"]:
        diff = "-" if c["편차"] is None else f"{c['편차']:.2f}%"
        lines.append(f"| {c['항목']} | {c['기간']} | {_big(c['기준'], c['통화'])} ({c['기준출처']}) | "
                     f"{_big(c['비교'], c['통화'])} ({c['비교출처']}) | {diff} | {c['판정']} |")
    if not sheet["checks"]:
        lines.append("| (교차 검증 없음) | | | | | |")

    if sheet["warnings"]:
        lines += ["", "## 경고"] + [f"- ⚠️ {w}" for w in sheet["warnings"]]
    lines += ["", "## 사용 규칙",
              "- 보고서와 Agent 분석의 정확한 수치는 이 표가 기준이다. 다른 출처 값이 다르면 **불일치로 표기**하고, "
              "두 값을 맞춘 숫자를 지어내지 않는다.",
              "- `데이터 없음` 칸은 추정으로 채우지 않는다. 필요하면 다른 출처에서 가져와 출처를 붙인다.",
              "- ❌ 판정 항목은 원본 공시로 확인하기 전까지 결론의 근거로 쓰지 않는다."]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description="팩트시트(확정 수치표) 생성.")
    p.add_argument("code", help="005930 / AAPL / 0700 등(global_stock_data 규칙)")
    p.add_argument("--years", type=int, default=3, help="연간 재무 연수(기본 3)")
    p.add_argument("--json", action="store_true", help="JSON 출력")
    a = p.parse_args()
    sheet = collect(a.code, a.years)
    print(json.dumps(sheet, ensure_ascii=False, indent=2) if a.json else render(sheet), end="")


if __name__ == "__main__":
    run(main)
