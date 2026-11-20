#!/usr/bin/env python3
"""미국 상장사 부실기업 스크리닝(/quality-screen 7지표) — SEC EDGAR XBRL 원본 기반, 외부 종속성 없음(stdlib만).

지표 계산·판정은 tools/quality_screen_kr.py 의 compute_metrics·judge 를 그대로 쓴다(한국 스크리닝과 같은 정의).
이 파일은 SEC companyfacts(10-K·20-F·40-F)를 그 함수의 입력 형식({연도: {계정: 값}})으로 바꾸는 어댑터다.

사용법:
    python3 tools/quality_screen_us.py AAPL MSFT COST                    # 개별 종목
    python3 tools/quality_screen_us.py --index SP500                     # S&P500 구성종목(위키백과 표)
    python3 tools/quality_screen_us.py --universe 스크리닝/나스닥100-후보풀/universe-20261119.json --json out.json
                                                                         # 구성종목 파일(나스닥100 등), 판정 전체 JSON 저장
    python3 tools/quality_screen_us.py --index SP500 --overrides 스크리닝/S&P500-후보풀/overrides-20261120.json
    python3 tools/quality_screen_us.py AAPL --as-of 2024-12-31           # 그 날까지 공시된 값만(시점 통제)

지표 정의는 quality_screen_kr.py 문서와 같다(① 10년 ROE, ② 5년 누적 FCF, ③ 최신 연도 이자보상, ④ 10년 매출총이익률,
⑤ 5년 OCF/순이익, ⑥ 10년 순이익률, ⑦ 5년 희석). 미국판에서 다른 점:
  - 기준 연도: 회사마다 as-of 시점까지 나온 최신 연간 보고서의 회계연도(회계연도 = 기간 종료일의 연도).
  - ⑦ 희석: 같은 10-K 안에서 전년 대비 희석 가중평균주식수 비율을 최근 5개 연도 이어 곱한다.
    10-K는 비교 연도를 분할 후 기준으로 다시 적으므로 주식분할이 희석으로 잡히지 않는다. 20% 초과는 M&A·상장 효과일 수 있어
    사람이 확인해 overrides "dilution_ok"로 통과 처리한다.
  - ② FCF: 영업현금흐름 − 유형자산 취득(무형자산 취득은 us-gaap에서 일관된 태그가 없어 빼지 않음).
  - 구성종목: --index SP500은 위키백과 표(GICS 섹터·하위업종 포함). 그 밖의 지수는 --universe 파일로 주고, 업종은 S&P500 표에서
    빌린다. S&P500에 없는 종목은 업종 미분류라 금융업·REIT 자동 분류가 안 되므로 overrides로 지정한다.
  - 금융업 자동 분류: GICS 하위업종이 은행·보험·증권·자산운용·소비자금융 등이면 ②~⑥ 해당없음(①·⑦로만 판정).
  - REIT: GICS 하위업종에 REIT가 들어가면 ①을 판정 제외('—'). 장부 ROE가 감가상각에 왜곡되고 핵심운영 ROE(FFO)는 계산하지 않음.
  - 면제 A의 '상장 10년 미만'은 최초 연간 보고서 접수일로 자동 판정한다. 합병·분사·본사 이전으로 CIK만 새로 생긴 경우는
    overrides "not_young"으로 뺀다.
  - 금액 단위: 공시 통화 그대로(대부분 USD, 20-F 제출사는 EUR 등). ② 칸에 통화를 표기.

overrides JSON(모두 선택, 키는 티커): quality_screen_kr.py 와 같은 키 +
  {"not_young": {티커: 사유}, "listed_under10": [티커], "financials": [티커], "nonfinancials": [티커],
   "reits": [티커], "nonreits": [티커], "costco_type": [티커], "dilution_ok": {티커: 사유},
   "cell_override": {티커: {"4": ["skip", "해당없음", "근거"]}}, "verdict_override": {티커: ["판정 보류", "근거"]}}
  dilution_ok 등 사유 값이 [상태, 사유] 리스트가 아니라 문자열이면 그대로 쓴다. "_"로 시작하는 키는 주석으로 무시한다.

원본 응답은 tools/.cache/ 에 캐시한다(sec_edgar_data.py 와 공유, 24시간). SEC는 연락처 있는 User-Agent를 요구한다
(환경변수 SEC_EDGAR_USER_AGENT). 교차 검증은 하지 않으므로 보고서에 쓰기 전 핵심 수치는 10-K 원본으로 확인한다.
종료 코드: 0 정상 / 2 인자 오류 / 4 출처 장애.
"""
import argparse
import html
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_screen_kr as kr  # noqa: E402
import sec_edgar_data as sec  # noqa: E402
from _us_common import NoDataError, UnavailableError, get_json, parse_as_of, read_cache, today, write_cache  # noqa: E402,F401

ANNUAL = ((300, 400),)
INSTANT = ((0, 0),)
FORMS = ("10-K", "20-F", "40-F")

# (키, 기간 종류, 태그 후보). sec_edgar_data.values_as_of 규칙: 앞 태그가 없는 기간만 뒤 태그로 채우고 합산하지 않는다.
# us-gaap 다음에 ifrs-full(20-F 제출사) 태그를 둔다.
TAGS = [
    ("rev", "d", ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                  "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense", "Revenue")),
    ("gp", "d", ("GrossProfit",)),
    ("cogs", "d", ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
                   "CostOfSales")),
    ("op", "d", ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")),
    ("pretax", "d", ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                     "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                     "ProfitLossBeforeTax")),
    ("ni", "d", ("ProfitLoss", "NetIncomeLoss")),
    ("ni_own", "d", ("NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic",
                     "ProfitLossAttributableToOwnersOfParent")),
    ("eq_own", "i", ("StockholdersEquity", "EquityAttributableToOwnersOfParent")),
    ("eq", "i", ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity",
                 "Equity")),
    ("int_is", "d", ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                     "InterestAndDebtExpense", "InterestExpenseNet", "FinanceCosts")),
    ("int_cf", "d", ("InterestPaidNet", "InterestPaid", "InterestPaidClassifiedAsOperatingActivities",
                     "InterestPaidClassifiedAsFinancingActivities")),
    ("ocf", "d", ("NetCashProvidedByUsedInOperatingActivities",
                  "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
                  "CashFlowsFromUsedInOperatingActivities")),
    ("capex_ppe", "d", ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
                        "PaymentsToAcquirePropertyPlantAndEquipmentAndOtherProductiveAssets",
                        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                        "PurchaseOfPropertyPlantAndEquipment")),
]
SHARE_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic",
              "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
              "AdjustedWeightedAverageShares", "WeightedAverageShares")
FIN_SUBS = ("Bank", "Insurance", "Reinsurance", "Investment Banking", "Asset Management", "Consumer Finance",
            "Multi-Sector Holdings", "Diversified Financial", "Mortgage")
COSTCO_SUBS = ("Consumer Staples Merchandise Retail", "Food Distributors", "Health Care Distributors",
               "Drug Retail", "Technology Distributors", "Food Retail", "Hypermarkets")
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
INDEXES = ("SP500",)


# ---------------------------------------------------------------------------
# SEC companyfacts → {연도: {계정: 값}} (순수 함수, 테스트 대상)
# ---------------------------------------------------------------------------

def merged_facts(facts: dict) -> dict:
    """companyfacts → 태그 이름: 사실. us-gaap를 먼저, 없는 태그만 ifrs-full에서 가져온다."""
    f = facts.get("facts") or {}
    out = dict(f.get("ifrs-full") or {})
    out.update(f.get("us-gaap") or {})
    return out


def fiscal_year(end: str) -> int:
    return int(end[:4])


def annual_data(g: dict, as_of: str):
    """→ ({회계연도: {계정: 값}}, 통화). 한 해에 종료일이 둘이면(회계연도 변경) 늦은 쪽."""
    data, currency = {}, "USD"
    for key, kind, tags in TAGS:
        vals, unit = sec.values_as_of(g, tags, as_of, INSTANT if kind == "i" else ANNUAL, FORMS)
        if key == "rev" and vals:
            currency = unit
        for (end, _), v in sorted(vals.items()):
            data.setdefault(fiscal_year(end), {})[key] = v
    return data, currency


def share_growth(g: dict, as_of: str, years: int = 5):
    """→ (최근 years개 연도 누적 증가율, 실제 이어 붙인 연도 수). 같은 연간 보고서 안의 전년 대비 비율만 쓴다."""
    for tag in SHARE_TAGS:
        units = (g.get(tag) or {}).get("units", {}).get("shares")
        if not units:
            continue
        by_accn = {}
        for f in units:
            if not f.get("form", "").startswith(FORMS) or f["filed"] > as_of or "start" not in f:
                continue
            days = (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days
            if not ANNUAL[0][0] <= days <= ANNUAL[0][1]:
                continue
            by_accn.setdefault(f["accn"], {"filed": f["filed"], "v": {}})["v"][fiscal_year(f["end"])] = f["val"]
        pairs = {}
        for rep in sorted(by_accn.values(), key=lambda r: r["filed"]):  # 나중 보고서(재작성)가 덮어씀
            ys = sorted(rep["v"])
            for p, c in zip(ys, ys[1:]):
                if c == p + 1 and rep["v"][p] > 0:
                    pairs[c] = rep["v"][c] / rep["v"][p]
        chain = sorted(pairs)[-years:]
        if len(chain) < 3:
            continue
        r = 1.0
        for y in chain:
            r *= pairs[y]
        return r - 1, len(chain)
    return None, 0


def first_annual_filed(g: dict) -> str:
    first = "9999-12-31"
    for tag in ("Assets", "NetIncomeLoss", "ProfitLoss"):
        for unit_values in ((g.get(tag) or {}).get("units") or {}).values():
            for f in unit_values:
                if f.get("form", "").startswith(FORMS):
                    first = min(first, f["filed"])
    return first


def years_before(as_of: str, n: int) -> str:
    d = date.fromisoformat(as_of)
    try:
        return d.replace(year=d.year - n).isoformat()
    except ValueError:  # 2월 29일
        return d.replace(year=d.year - n, day=28).isoformat()


def classify(sub: str) -> dict:
    sub = sub or ""
    return {"financial": any(s in sub for s in FIN_SUBS), "reit": "REIT" in sub,
            "costco_candidate": any(s in sub for s in COSTCO_SUBS)}


def negative_equity_profitable(data: dict, base: int) -> bool:
    """최근 10년 중 자본이 있는 해가 모두 음(-)이고 최근 5년 순이익 합계가 흑자인가(AZO·YUM형 자사주 매입 기업)."""
    eqs = [data[y]["eq_own"] for y in data if base - 9 <= y <= base and "eq_own" in data[y]]
    ni5 = [data[y].get("ni_own", data[y].get("ni")) for y in range(base - 4, base + 1) if y in data]
    ni5 = [v for v in ni5 if v is not None]
    return bool(eqs) and all(e <= 0 for e in eqs) and bool(ni5) and sum(ni5) > 0


def evaluate(ticker: str, g: dict, as_of: str, info: dict, ov: dict) -> dict:
    """한 종목: SEC 사실 → kr.compute_metrics·judge 결과 + 미국판 메타데이터."""
    data, currency = annual_data(g, as_of)
    ni_years = sorted(y for y, r in data.items() if "ni" in r or "ni_own" in r)
    if not ni_years:
        raise NoDataError(f"{ticker}: as-of {as_of}까지 연간 순이익 공시 없음")
    base = ni_years[-1]
    if base < int(as_of[:4]) - 2:
        raise NoDataError(f"{ticker}: 최신 연간 순이익이 {base}년 — 최근 공시 없음(태그 변경·상장폐지 가능)")
    for r in data.values():  # 연결 순이익만 있거나 지배주주 순이익만 있는 경우 서로 채움(kr.merge_reports와 같은 처리)
        if "ni" not in r and "ni_own" in r:
            r["ni"] = r["ni_own"]
        if "ni_own" not in r and "ni" in r:
            r["ni_own"] = r["ni"]
        if "gp" not in r and r.get("rev") and r.get("cogs"):
            r["gp"] = r["rev"] - r["cogs"]
        if "eq_own" not in r and "eq" in r:  # 지배주주 자본 태그가 없으면 총자본(kr.merge_reports와 같은 처리)
            r["eq_own"] = r["eq"]
        if "op" not in r and "pretax" in r:  # 영업이익 미공시(REIT·지주사 등): 세전이익 + 이자비용으로 EBIT 근사
            r["op"] = r["pretax"] + abs(r.get("int_is") or r.get("int_cf") or 0)
    growth, chained = share_growth(g, as_of)
    m = kr.compute_metrics(data, base, 1.0 if growth is not None else None,
                           1.0 + growth if growth is not None else None)
    m["listed_recently"] = growth is None and len(ni_years) < 5
    m["dilution_years"] = chained

    cls = classify(info.get("sub", ""))
    lst = lambda k: set(ov.get(k, []))  # noqa: E731
    financial = ticker in lst("financials") or (cls["financial"] and ticker not in lst("nonfinancials"))
    reit = ticker in lst("reits") or (cls["reit"] and ticker not in lst("nonreits"))
    first = first_annual_filed(g)
    auto_young = first > years_before(as_of, 10)
    young = ticker in lst("listed_under10") or (auto_young and ticker not in set(ov.get("not_young", {})))
    cells = {str(k): v for k, v in (ov.get("cell_override", {}).get(ticker) or {}).items()}
    if reit and "1" not in cells:
        cells["1"] = ["skip", "REIT 제외", "장부 ROE 감가상각 왜곡 — 핵심운영 ROE 미산정"]
    elif m.get("roe10") is None and "1" not in cells and negative_equity_profitable(data, base):
        cells["1"] = ["warn", "음(-)자본", "자사주 매입으로 자본이 음수 — ROE 산정 불가, 최근 5년 순이익 흑자라 배제하지 않음"]
    dil = ov.get("dilution_ok", {}).get(ticker)
    j = kr.judge(m, financial=financial, young=young, costco_type=ticker in lst("costco_type"),
                 dilution_ok=dil, cell_override=cells, verdict_override=ov.get("verdict_override", {}).get(ticker))
    f = m.get("fcf5")
    if j["cells"][2]["s"] in ("pass", "fail") and f is not None and "2" not in cells:
        j["cells"][2]["t"] = f"{f / 1e9:+,.1f}B {currency}" if currency != "USD" else f"{f / 1e9:+,.1f}B"
    if j["cells"][7]["s"] == "fail":
        j["flags"].append("⑦ M&A·상장 효과 확인 필요")
    if cls["costco_candidate"] and ticker not in lst("costco_type") and any(
            j["cells"][k]["s"] == "fail" for k in (4, 6)):
        j["flags"].append("면제 C 후보 업종 — 사업모델 확인 후 costco_type")
    j.update(code=ticker, name=info.get("name") or ticker, sector=info.get("sector", ""), sub=info.get("sub", ""),
             financial=financial, reit=reit, young=young, first_annual_filed=first, fiscal_year=base,
             currency=currency, mcap_eok=None, metrics=m)
    return j


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

def parse_constituents(page: str) -> list:
    """위키백과 구성종목표 → [{ticker, name, sector, sub}].

    표 id가 페이지마다 다르므로(S&P500은 "constituents", 나스닥100은 자동 id) 머리글에 티커·GICS 섹터 열이 있는
    첫 wikitable을 쓴다."""
    for table in re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>', page, re.S):
        head = [re.sub(r"<[^>]+>", "", h).strip().lower() for h in
                re.findall(r"<th[^>]*>(.*?)</th>", table.split("</tr>", 1)[0], re.S)]
        col = lambda *names: next((i for i, h in enumerate(head) if any(n in h for n in names)), None)  # noqa: E731
        ci, cn, cs, cb = col("symbol", "ticker"), col("security", "company"), col("gics sector"), col("sub-industry")
        if ci is None or cn is None or cs is None:
            continue
        out = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            if len(cells) <= max(i for i in (ci, cn, cs, cb) if i is not None) or cells[ci].lower() in ("symbol", "ticker"):
                continue
            out.append({"ticker": cells[ci], "name": cells[cn], "sector": cells[cs],
                        "sub": cells[cb] if cb is not None else ""})
        if out:
            return out
    raise UnavailableError("티커·GICS 섹터 열이 있는 구성종목표를 찾지 못함 — 위키백과 페이지 구조 변경")


def _get_text(url: str) -> str:
    status, body = http_get(url, headers={"User-Agent": "ai-berkshire-fork quality screen (research tool)"})
    if status != 200:
        raise UnavailableError(f"구성종목 조회 실패({url}): HTTP {status}")
    return body


def fetch_index(index: str) -> list:
    """SP500: 위키백과 구성종목표(GICS 섹터·하위업종 포함). 그 밖의 지수는 --universe 파일로 준다."""
    index = index.upper()
    if index not in INDEXES:
        raise SystemExit(f"--index 는 {', '.join(INDEXES)}만 지원 — 다른 지수는 --universe 파일로 지정")
    name = f"qs_us_index_{index}_{today()}.json"
    cached = read_cache(name, 24 * 3600)
    if cached is not None:
        return cached
    rows = parse_constituents(_get_text(SP500_URL))
    write_cache(name, rows)
    return rows


def load_universe(path: str) -> list:
    """구성종목 파일: [{"ticker", "name"?, "sector"?, "sub"?}] 또는 {"constituents": [...]} 또는 티커 문자열 목록.
    업종이 비어 있는 종목은 S&P500 표에서 채운다(조회 실패 시 빈칸)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    rows = raw.get("constituents", []) if isinstance(raw, dict) else raw
    rows = [{"ticker": r} if isinstance(r, str) else r for r in rows]
    gics = {}
    if any(not r.get("sub") for r in rows):
        try:
            gics = {s["ticker"]: s for s in fetch_index("SP500")}
        except UnavailableError as e:
            print(f"⚠️ S&P500 표 조회 실패 — 업종 자동 분류 없이 진행: {e}", file=sys.stderr)
    out = []
    for r in rows:
        t = r["ticker"].strip().upper()
        g = gics.get(t, {})
        out.append({"ticker": t, "name": r.get("name") or g.get("name", ""),
                    "sector": r.get("sector") or g.get("sector", ""), "sub": r.get("sub") or g.get("sub", "")})
    return out


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def lookup(tickers: list, known: set) -> list:
    """개별 티커에 S&P500 표의 GICS 섹터·하위업종을 붙인다(금융업·REIT 자동 분류에 필요).
    표에 없거나 조회에 실패하면 분류 없이 진행한다 — 그때는 overrides financials·reits로 지정."""
    wanted = [t.upper() for t in tickers if t.upper() not in known]
    table = {}
    if wanted:
        try:
            table = {s["ticker"]: s for s in fetch_index("SP500")}
        except UnavailableError as e:
            print(f"⚠️ S&P500 구성종목표 조회 실패 — 업종 자동 분류 없이 진행: {e}", file=sys.stderr)
    return [table.get(t) or {"ticker": t, "name": "", "sector": "", "sub": ""} for t in wanted]


def load_facts(ticker: str) -> dict:
    """티커 → companyfacts. 같은 CIK(GOOGL·GOOG)를 두 스레드가 동시에 캐시에 쓰면 Windows에서 교체가 실패하므로 CIK별로 잠근다."""
    cik, _ = sec.resolve(ticker.replace(".", "-"))
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(cik, threading.Lock())
    with lock:
        return sec._cached_json(sec._FACTS_URL.format(cik=cik), f"sec_CIK{cik}.json")


def load_overrides(path: str) -> dict:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        ov = json.load(f)
    return {k: v for k, v in ov.items() if not k.startswith("_")}


def screen(stocks: list, as_of: str, ov: dict, workers: int = 4, log=print) -> dict:
    def one(s):
        t = s["ticker"]
        try:
            return t, evaluate(t, merged_facts(load_facts(t)), as_of, s, ov)
        except (NoDataError, UnavailableError) as e:
            return t, {"code": t, "name": s.get("name") or t, "sector": s.get("sector", ""), "error": str(e)}

    sec._cached_json(sec._TICKERS_URL, "sec_company_tickers.json")  # 티커표는 스레드 시작 전에 한 번만 받는다
    out = {}
    with ThreadPoolExecutor(workers) as ex:
        for i, (t, j) in enumerate(ex.map(one, stocks), 1):
            out[t] = j
            if i % 50 == 0:
                log(f"  처리 {i}/{len(stocks)}")
    return out


def render(result: dict) -> str:
    ok = {t: j for t, j in result.items() if "error" not in j}
    text = kr.render(ok).replace("| 기업 (코드) |", "| 기업 (티커) |")
    err = [j for j in result.values() if "error" in j]
    if err:
        text += "\n\n데이터 부족(판정 불가):\n" + "\n".join(f"- {j['name']} ({j['code']}): {j['error']}" for j in err)
    flagged = [j for j in ok.values() if any(f.startswith(("⑦", "면제 C")) for f in j["flags"])]
    if flagged:
        text += "\n\n수작업 확인 대상:\n" + "\n".join(
            f"- {j['name']} ({j['code']}): " + ", ".join(f for f in j["flags"] if f.startswith(("⑦", "면제 C")))
            + (f" — 희석 {j['cells'][7]['t']}" if j["cells"][7]["s"] == "fail" else "") for j in flagged)
    return text


def main():
    p = argparse.ArgumentParser(description="미국 상장사 부실기업 스크리닝(7지표, SEC EDGAR XBRL 원본).")
    p.add_argument("tickers", nargs="*", help="티커(여러 개)")
    p.add_argument("--index", default="", help="SP500(위키백과 구성종목표)")
    p.add_argument("--universe", default="", help="구성종목 JSON 파일(예: 나스닥100 — 스크리닝/나스닥100-후보풀/universe-*.json)")
    p.add_argument("--as-of", default="", help="이 날짜(YYYY-MM-DD)까지 공시된 값만 사용(기본: 오늘)")
    p.add_argument("--overrides", default="", help="수작업 판단 JSON 경로")
    p.add_argument("--json", default="", help="판정 전체를 저장할 JSON 경로")
    p.add_argument("--workers", type=int, default=4, help="동시 요청 수(기본 4, SEC 한도 초당 10건)")
    a = p.parse_args()
    if not a.tickers and not a.index and not a.universe:
        p.error("티커, --index 또는 --universe 가 필요합니다")
    as_of = parse_as_of(a.as_of) if a.as_of else today()
    try:
        stocks = fetch_index(a.index) if a.index else []
        if a.universe:
            seen = {s["ticker"] for s in stocks}
            stocks += [s for s in load_universe(a.universe) if s["ticker"] not in seen]
        stocks += lookup(a.tickers, {s["ticker"] for s in stocks})
        ov = load_overrides(a.overrides)
        print(f"as-of {as_of} · 대상 {len(stocks)}개 · SEC EDGAR 수집 중", file=sys.stderr)
        result = screen(stocks, as_of, ov, a.workers, log=lambda s: print(s, file=sys.stderr))
    except UnavailableError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(4)
    print(render(result))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1, default=str)
        print(f"\nJSON 저장: {a.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
