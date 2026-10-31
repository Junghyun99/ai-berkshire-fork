#!/usr/bin/env python3
"""한국 상장사 부실기업 스크리닝(/quality-screen 7지표) — DART 원본 재무 기반, 외부 종속성 없음(stdlib만).

.claude/skills/quality-screen 의 7가지 배제 지표와 3가지 면제 규칙을 DART 사업보고서 원본으로 계산한다.
WebSearch로 종목마다 수치를 모으는 대신, 공시 재무제표에서 같은 정의로 한꺼번에 계산해
지수·업종 단위 일괄 스크리닝을 재현 가능하게 만든다.

사용법:
    python3 tools/quality_screen_kr.py 005930 000660 035420            # 개별 종목
    python3 tools/quality_screen_kr.py --index KPI200                    # 네이버 증권 지수 구성종목(KPI200 등)
    python3 tools/quality_screen_kr.py --index KPI200 --json out.json    # 판정 전체를 JSON으로 저장
    python3 tools/quality_screen_kr.py 005930 --year 2024                # 기준 사업연도 지정(기본: 직전 공시 연도)
    python3 tools/quality_screen_kr.py --index KPI200 --overrides ov.json  # 수작업 판단 반영

지표 정의(기준 사업연도 Y):
  ① ROE        Y-9~Y 연도별 지배주주순이익 ÷ 평균 지배주주자본의 단순평균(< 8% 배제)
  ② FCF        Y-4~Y 누적(영업CF − 유형자산 취득 − 무형자산 취득)(< 0 배제)
  ③ 이자보상   Y 영업이익 ÷ 이자비용(IS 이자비용, 없으면 CF 이자지급)(< 2배 또는 영업적자 배제)
  ④ 매출총이익률 Y-9~Y 누계 매출총이익 ÷ 누계 매출(< 15% 배제, 원가 미구분 업종은 판정 제외)
  ⑤ OCF/NI     Y-4~Y 누적 영업CF ÷ 누적 순이익(< 0.7 또는 누적 적자 배제)
  ⑥ 순이익률   Y-9~Y 누계 순이익 ÷ 누계 매출(< 5% 배제)
  ⑦ 희석       Y-5→Y 발행주식 총수 증가율(> 20% 배제). 액면분할·무상증자·합병은 기계적으로 구분할 수 없어
               20% 초과 종목은 DART 주요사항보고서 제목을 함께 출력한다. 비희석 사유가 확인되면 overrides로 통과 처리.
  면제 A(① 면제) 상장 10년 미만·최근 5년 매출총이익률 > 30%·최근 2년 영업CF 흑자 — 상장 10년 미만은 overrides "listed_under10"
  면제 B(⑥ 면제) 최근 5년 매출총이익률 > 30%·최근 2년 순이익률 5% 이상(또는 Y가 5% 이상이면서 상승)
  면제 C(④⑥ 면제) ROE > 20%·OCF/NI > 1.0·멤버십/박리다매형 — 사업모델은 overrides "costco_type"

금융업(은행·금융지주·보험·증권·카드, KSIC 641·6491·65·6612, 64992 중 사명에 '금융'):
  ②~⑥은 사업구조상 무의미해 적용하지 않고 ①·⑦로만 판정한다. DART API가 금융업의 2020년 이전
  재무제표를 주지 않아 ROE는 가용 연도(대개 5년) 평균이 된다.

외화 표시(예: 두산밥캣 2023~ USD): 보고서 currency 필드로 감지해 FRED DEXKOUS 연평균으로 환산한다
(FRED_API_KEY 필요, 재무상태표도 근사로 연평균 사용). 키가 없으면 해당 종목을 판정 보류로 둔다.

overrides JSON(모두 선택):
  {"financials": [코드], "nonfinancials": [코드], "listed_under10": [코드], "costco_type": [코드],
   "dilution_ok": {코드: 사유}, "cell_override": {코드: {"5": ["adj", "1.69", "근거"]}},
   "verdict_override": {코드: ["판정 보류", "근거"]}}

원본 응답은 tools/.cache/quality_screen/ 에 캐시한다(재실행 시 API 호출 없음, --refresh 로 무시).
네이버 증권 재무 교차 검증은 하지 않으므로, 보고서에 쓰기 전 핵심 수치는 별도 출처로 확인한다.
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dart_data  # noqa: E402

CACHE = os.path.join(dart_data._CACHE_DIR, "quality_screen")
COLS = ("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")
_REFRESH = False

# (키, sj_div 우선순위, XBRL account_id 후보, 정규화 계정명 후보). account_id 매칭이 먼저다.
RULES = [
    ("rev", ("IS", "CIS"), ("ifrs-full_Revenue",), ("매출액", "영업수익", "수익매출액", "매출", "수익")),
    ("gp", ("IS", "CIS"), ("ifrs-full_GrossProfit",), ("매출총이익", "매출총이익손실", "매출총손익")),
    ("cogs", ("IS", "CIS"), ("ifrs-full_CostOfSales",), ("매출원가",)),
    ("op", ("IS", "CIS"), ("dart_OperatingIncomeLoss",), ("영업이익", "영업이익손실", "영업손익", "영업손실")),
    ("ni", ("IS", "CIS"), ("ifrs-full_ProfitLoss",), ("당기순이익", "당기순이익손실", "연결당기순이익", "당기순손익")),
    ("ni_own", ("IS", "CIS"), ("ifrs-full_ProfitLossAttributableToOwnersOfParent",), ()),
    # 지배지분 자본은 계정명 매칭을 하지 않는다(자본금 등 다른 줄이 같은 이름으로 잡히는 사례가 있음)
    ("eq_own", ("BS",), ("ifrs-full_EquityAttributableToOwnersOfParent",), ()),
    ("eq", ("BS",), ("ifrs-full_Equity",), ("자본총계",)),
    ("int_is", ("IS", "CIS"), ("ifrs-full_InterestExpense", "dart_InterestExpense",
                               "ifrs-full_InterestExpenseOnBorrowings"), ("이자비용",)),
    ("fincost", ("IS", "CIS"), ("ifrs-full_FinanceCosts",), ("금융비용", "금융원가")),
    ("int_cf", ("CF",), ("ifrs-full_InterestPaidClassifiedAsOperatingActivities",
                         "ifrs-full_InterestPaidClassifiedAsFinancingActivities", "ifrs-full_InterestPaid"),
        ("이자의지급", "이자지급", "이자의지급액", "이자지급액")),
    ("ocf", ("CF",), ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
        ("영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동순현금흐름", "영업활동으로인한순현금흐름")),
    ("capex_ppe", ("CF",), ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                            "ifrs-full_PurchaseOfPropertyPlantAndEquipment"),
        ("유형자산의취득", "유형자산취득", "유형자산의증가")),
    ("capex_int", ("CF",), ("ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
                            "ifrs-full_PurchaseOfIntangibleAssets"),
        ("무형자산의취득", "무형자산취득", "무형자산의증가")),
]
MULTI_KEYS = {"매출액": "rev", "영업이익": "op", "당기순이익": "ni", "당기순이익(손실)": "ni", "자본총계": "eq"}
DILUTION_PAT = re.compile(r"무상증자|주식분할|액면분할|유상증자|합병|주식교환|분할결정|전환|신주인수권|감자|주식배당")


# ---------------------------------------------------------------------------
# 수집(캐시)
# ---------------------------------------------------------------------------

def _cached(endpoint: str, params: dict, name: str) -> dict:
    """DART 응답을 캐시. 정상(000)·데이터 없음(013)만 캐시하고, 요청 제한(020)은 기다렸다 재시도."""
    path = os.path.join(CACHE, name)
    if not _REFRESH and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("status") in ("000", "013"):
                return d
        except ValueError:
            pass
    url = f"{dart_data._BASE}/{endpoint}?{urlencode(dict(params, crtfc_key=dart_data._api_key()))}"
    for attempt in range(4):
        r = subprocess.run(["curl", "-sS", "-m", "90", url], capture_output=True)
        try:
            d = json.loads(r.stdout.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            time.sleep(2 ** attempt)
            continue
        if d.get("status") == "020":
            time.sleep(30)
            continue
        if d.get("status") in ("000", "013"):
            os.makedirs(CACHE, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        return d
    return {"status": "ERR"}


def report_years(base: int):
    """사업보고서 1건이 3개년을 주므로 Y, Y-3, Y-6, Y-9 로 Y-11~Y 를 덮는다."""
    return (base, base - 3, base - 6, base - 9)


def collect(code: str, corp_code: str, base: int, financial_hint: bool):
    """종목 1개의 원본 응답을 캐시에 채운다."""
    _cached("company.json", {"corp_code": corp_code}, f"{code}_company.json")
    years = list(report_years(base)) + ([base - 2] if financial_hint else [])
    for y in years:
        p = {"corp_code": corp_code, "bsns_year": y, "reprt_code": "11011"}
        if _cached("fnlttSinglAcntAll.json", dict(p, fs_div="CFS"), f"{code}_{y}_CFS.json").get("status") != "000":
            _cached("fnlttSinglAcntAll.json", dict(p, fs_div="OFS"), f"{code}_{y}_OFS.json")
    for y in (base - 5, base):
        _cached("stockTotqySttus.json", {"corp_code": corp_code, "bsns_year": y, "reprt_code": "11011"},
                f"{code}_{y}_shares.json")


def collect_multi(corp_codes: list, base: int):
    """주요계정 다중조회(100사씩) — 전체 재무제표가 빠진 해를 매출·영업이익·순이익·자본총계로 보충."""
    for ry in report_years(base)[1:]:
        for i in range(0, len(corp_codes), 100):
            chunk = corp_codes[i:i + 100]
            tag = hashlib.md5(",".join(chunk).encode()).hexdigest()[:10]
            _cached("fnlttMultiAcnt.json", {"corp_code": ",".join(chunk), "bsns_year": ry, "reprt_code": "11011"},
                    f"MULTI_{ry}_{tag}.json")


def fetch_index(index: str) -> list:
    """네이버 증권 모바일 API로 지수 구성종목 [{code, name, mcap_eok}]."""
    out = {}
    for page in range(1, 11):
        r = subprocess.run(["curl", "-sS", "-m", "30",
                            f"https://m.stock.naver.com/api/index/{index}/enrollStocks?page={page}&pageSize=60"],
                           capture_output=True)
        try:
            rows = json.loads(r.stdout.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ConnectionError(f"{index} 구성종목 조회 실패(page {page})")
        if not rows:
            break
        for x in rows:
            out[x["itemCode"]] = {"code": x["itemCode"], "name": x["stockName"],
                                  "mcap_eok": dart_data._parse_amount(x.get("marketValue"))}
        if len(rows) < 60:  # pageSize 100은 빈 응답을 준다
            break
    return list(out.values())


def fred_usdkrw(years) -> dict:
    """FRED DEXKOUS 연평균 원/달러. 키가 없거나 실패하면 {}."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key or not years:
        return {}
    q = {"series_id": "DEXKOUS", "api_key": key, "file_type": "json", "frequency": "a",
         "aggregation_method": "avg", "observation_start": f"{min(years)}-01-01",
         "observation_end": f"{max(years)}-12-31"}
    r = subprocess.run(["curl", "-sS", "-m", "30",
                        "https://api.stlouisfed.org/fred/series/observations?" + urlencode(q)], capture_output=True)
    try:
        obs = json.loads(r.stdout.decode("utf-8")).get("observations") or []
    except (ValueError, UnicodeDecodeError):
        return {}
    return {int(o["date"][:4]): float(o["value"]) for o in obs if o.get("value") not in (None, ".")}


# ---------------------------------------------------------------------------
# 추출(순수 함수)
# ---------------------------------------------------------------------------

def num(s):
    """DART 금액 문자열 → float. '(1,234)' 음수 표기도 처리."""
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    v = dart_data._parse_amount(s.strip("()"))
    return -v if (neg and v is not None) else v


def extract(items: list) -> dict:
    """fnlttSinglAcntAll list → {키: [당기, 전기, 전전기]}."""
    out = {}
    for key, sjs, ids, names in RULES:
        hit = None
        for sj in sjs:
            hit = next((it for it in items if it.get("sj_div") == sj and it.get("account_id") in ids), None)
            if hit:
                break
        if not hit and names:
            for sj in sjs:
                hit = next((it for it in items
                            if it.get("sj_div") == sj and dart_data._norm(it.get("account_nm")) in names), None)
                if hit:
                    break
        if hit:
            out[key] = [num(hit.get(c)) for c in COLS]
    return out


def merge_reports(reports: list, multi: dict = None, fx: dict = None):
    """보고서들 → {연도: {계정: 값}}, {연도: 기준}.

    reports: [(사업연도, fs_div, currency, items)] 를 최신 보고서부터. 같은 해는 최신 보고서(재작성) 값을 쓰고
    빈 계정만 옛 보고서로 보충한다. multi: {연도: ({계정: 값}, fs_div)} — 전체 재무제표가 없는 해만 채운다.
    fx: {연도: 원/달러} — 통화가 KRW가 아닌 보고서의 금액을 환산. 환율이 없으면 그 해를 'fx_missing'에 담는다.
    """
    data, basis, fx_missing = {}, {}, set()
    for ry, fs, cur, items in sorted(reports, key=lambda r: -r[0]):
        ex = extract(items)
        for i, y in enumerate((ry, ry - 1, ry - 2)):
            row = {k: v[i] for k, v in ex.items() if v[i] is not None}
            if not row:
                continue
            if cur and cur != "KRW":
                rate = (fx or {}).get(y)
                if rate is None:
                    fx_missing.add(y)
                    continue
                row = {k: v * rate for k, v in row.items()}
            if y in data:
                for k, v in row.items():
                    data[y].setdefault(k, v)
            else:
                data[y], basis[y] = row, fs + ("" if not cur or cur == "KRW" else f"-{cur}환산")
    for y, (row, fs) in (multi or {}).items():
        if y not in data and y not in fx_missing:
            data[y], basis[y] = dict(row), fs + "-주요계정"
    for r in data.values():
        if r.get("cogs") == 0 or (r.get("gp") is not None and r.get("rev") and abs(r["gp"] - r["rev"]) < 1):
            r.pop("gp", None)
            r.pop("cogs", None)  # 매출원가 미구분(영업수익=매출총이익)
        if "gp" not in r and r.get("rev") and r.get("cogs"):
            r["gp"] = r["rev"] - r["cogs"]
        if "ni_own" not in r and "ni" in r:
            r["ni_own"] = r["ni"]
        # 지배지분 자본이 총자본의 30% 미만인데 순이익은 대부분 지배주주 몫이면 태깅 오류로 보고 총자본 사용
        if "eq" in r and ("eq_own" not in r or (r["eq_own"] < 0.3 * r["eq"] and r.get("ni")
                                                 and r.get("ni_own", 0) >= 0.6 * r["ni"])):
            r["eq_own"] = r["eq"]
    return data, basis, sorted(fx_missing)


def total_shares(items: list):
    """stockTotqySttus list → 발행주식 총수(보통+우선)."""
    for r in items or []:
        if r.get("se") == "합계":
            v = num(r.get("istc_totqy"))
            if v:
                return v
    return sum(num(r.get("istc_totqy")) or 0 for r in items or [] if r.get("se") in ("보통주", "우선주")) or None


# ---------------------------------------------------------------------------
# 지표·판정(순수 함수)
# ---------------------------------------------------------------------------

def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def compute_metrics(data: dict, base: int, shares_then=None, shares_now=None) -> dict:
    """연도별 계정 → 7개 지표 원값."""
    ys = sorted(data)
    long_ys = [y for y in ys if base - 9 <= y <= base]
    recent = list(range(base - 4, base + 1))
    m = {"years": ys}
    roes = {}
    for y in long_ys:
        r = data[y]
        e1, e0 = r.get("eq_own"), data.get(y - 1, {}).get("eq_own")
        if r.get("ni_own") is None or not e1:
            continue
        b = (e1 + e0) / 2 if e0 else e1
        if b > 0:
            roes[y] = r["ni_own"] / b
    m["roe_by_year"] = roes
    m["roe10"] = _avg(roes.values())
    m["roe_median"] = statistics.median(roes.values()) if roes else None
    fy = [y for y in recent if "ocf" in data.get(y, {})]
    m["fcf5"] = sum(data[y]["ocf"] - abs(data[y].get("capex_ppe", 0)) - abs(data[y].get("capex_int", 0))
                    for y in fy) if fy else None
    ly = max((y for y in ys if y <= base and "op" in data[y]), default=None)
    m["op_latest"] = data[ly]["op"] if ly else None
    m["icr"] = m["interest"] = None
    if ly:
        r = data[ly]
        interest = next((r[k] for k in ("int_is", "int_cf", "fincost") if r.get(k)), None)
        m["interest"] = abs(interest) if interest else None
        m["icr"] = r["op"] / abs(interest) if interest else None

    def agg(key, yrs):
        yrs = [y for y in yrs if data.get(y, {}).get("rev") and key in data[y]]
        return sum(data[y][key] for y in yrs) / sum(data[y]["rev"] for y in yrs) if yrs else None

    m["gm10"], m["gm5"] = agg("gp", long_ys), agg("gp", recent)
    m["nm10"], m["nm5"] = agg("ni", long_ys), agg("ni", recent)
    if m["gm10"] is not None and m["gm10"] > 0.95:
        m["gm10"] = m["gm5"] = None  # 영업수익=매출총이익 구조
    nm = {y: data[y]["ni"] / data[y]["rev"] for y in ys if data[y].get("rev") and "ni" in data[y]}
    m["nm_recent"] = [nm.get(base - 1), nm.get(base)]
    oy = [y for y in recent if "ocf" in data.get(y, {}) and "ni" in data[y]]
    m["ni5_sum"] = sum(data[y]["ni"] for y in oy) if oy else None
    m["ocfni5"] = (sum(data[y]["ocf"] for y in oy) / m["ni5_sum"]) if oy and m["ni5_sum"] and m["ni5_sum"] > 0 else None
    m["ocf_recent"] = [data.get(base - 1, {}).get("ocf"), data.get(base, {}).get("ocf")]
    m["dilution5"] = (shares_now / shares_then - 1) if shares_then and shares_now else None
    m["listed_recently"] = bool(shares_now and not shares_then)
    m["short_history"] = len(long_ys) < 5
    return m


def _cell(state, text, note=""):
    return {"s": state, "t": text, "note": note}


def judge(m: dict, financial=False, young=False, costco_type=False, dilution_ok=None,
          cell_override=None, verdict_override=None) -> dict:
    """지표 → 칸별 판정(pass/warn/fail/na/skip/exempt/adj)과 결과."""
    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    r = {}
    roe = m.get("roe10")
    r[1] = (_cell("na", "데이터 부족") if roe is None else _cell("fail", pct(roe)) if roe < 0.08
            else _cell("warn", pct(roe)) if roe < 0.09 else _cell("pass", pct(roe)))
    if financial:
        for k in (2, 3, 4, 5, 6):
            r[k] = _cell("skip", "해당없음")
    else:
        f = m.get("fcf5")
        r[2] = _cell("na", "데이터 부족") if f is None else _cell("fail" if f < 0 else "pass", f"{f / 1e12:+.2f}조")
        icr, op = m.get("icr"), m.get("op_latest")
        if op is None:
            r[3] = _cell("na", "데이터 부족")
        elif op < 0:
            r[3] = _cell("fail", "영업적자")
        elif icr is None:
            r[3] = _cell("pass", "무차입")
        else:
            r[3] = _cell("fail" if icr < 2 else "warn" if icr < 3 else "pass",
                         f"{icr:.0f}배" if icr >= 10 else f"{icr:.1f}배")
        gm = m.get("gm10")
        r[4] = (_cell("na", "원가 미구분") if gm is None else _cell("fail", pct(gm)) if gm < 0.15
                else _cell("warn", pct(gm)) if gm < 0.17 else _cell("pass", pct(gm)))
        o = m.get("ocfni5")
        if o is None:
            r[5] = _cell("fail", "누적적자") if m.get("ni5_sum") is not None else _cell("na", "데이터 부족")
        else:
            r[5] = _cell("fail" if o < 0.7 else "warn" if o < 0.8 else "pass", f"{o:.2f}")
        nmv = m.get("nm10")
        r[6] = (_cell("na", "데이터 부족") if nmv is None else _cell("fail", pct(nmv)) if nmv < 0.05
                else _cell("warn", pct(nmv)) if nmv < 0.06 else _cell("pass", pct(nmv)))
    d = m.get("dilution5")
    if d is None:
        r[7] = _cell("na", "상장 5년 미만" if m.get("listed_recently") else "데이터 부족")
    elif d > 0.20:
        r[7] = _cell("pass", f"{d * 100:+.0f}%*", dilution_ok) if dilution_ok else _cell("fail", f"{d * 100:+.0f}%")
    else:
        r[7] = _cell("warn" if d > 0.15 else "pass", f"{d * 100:+.0f}%")

    exempt = []
    gm5 = m.get("gm5")
    o1, o2 = m.get("ocf_recent") or [None, None]
    n1, n2 = m.get("nm_recent") or [None, None]
    if r[1]["s"] == "fail" and young and gm5 and gm5 > 0.30 and o1 and o2 and o1 > 0 and o2 > 0:
        r[1]["s"] = "exempt"
        exempt.append("A")
    if not financial and r[6]["s"] == "fail" and gm5 and gm5 > 0.30 and n2 is not None and n2 >= 0.05 \
            and n1 is not None and (n1 >= 0.05 or n2 > n1):
        r[6]["s"] = "exempt"
        exempt.append("B")
    if not financial and costco_type and (r[4]["s"] == "fail" or r[6]["s"] == "fail") \
            and (m.get("roe10") or 0) > 0.20 and (m.get("ocfni5") or 0) > 1.0:
        for k in (4, 6):
            if r[k]["s"] == "fail":
                r[k]["s"] = "exempt"
        exempt.append("C")
    for k, (st, txt, note) in (cell_override or {}).items():
        r[int(k)] = _cell(st, txt, note)

    states = [c["s"] for c in r.values()]
    if "fail" in states:
        verdict = "배제"
    elif r[1]["s"] == "na" or states.count("na") >= 2:
        verdict = "판정 보류"
    elif "exempt" in states or "adj" in states:
        verdict = "면제 통과"
    else:
        verdict = "통과"
    reason = ""
    if verdict_override:
        verdict, reason = verdict_override
    flags = ["데이터 기간 부족"] if m.get("short_history") else []
    if m.get("roe10") is not None and m.get("roe_median") is not None and abs(m["roe10"] - m["roe_median"]) > 0.04:
        flags.append("ROE 평균·중앙값 괴리(일회성 확인)")
    return {"cells": r, "verdict": verdict, "exempt": exempt, "flags": flags, "reason": reason,
            "fails": [k for k, c in r.items() if c["s"] == "fail"]}


def is_financial(induty: str, name: str) -> bool:
    induty = induty or ""
    return induty.startswith(("641", "6491", "65", "6612")) or (induty.startswith("64992") and "금융" in (name or ""))


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def _load(name):
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError:
        return None
    return d if d.get("status") == "000" else None


def _multi_rows(code: str, base: int) -> dict:
    out = {}
    for ry in report_years(base)[1:]:
        items = []
        for f in os.listdir(CACHE) if os.path.isdir(CACHE) else []:
            if f.startswith(f"MULTI_{ry}_"):
                d = _load(f) or {}
                items += [it for it in d.get("list") or [] if it.get("stock_code") == code]
        for fs in ("CFS", "OFS"):
            sel = [it for it in items if it.get("fs_div") == fs]
            if not sel:
                continue
            for i, y in enumerate((ry, ry - 1, ry - 2)):
                row = {}
                for it in sel:
                    k, v = MULTI_KEYS.get(it.get("account_nm")), num(it.get(COLS[i]))
                    if k and v is not None:
                        row.setdefault(k, v)
                if row and y not in out:
                    out[y] = (row, fs)
            break
    return out


def dilution_disclosures(corp_code: str, base: int) -> list:
    """희석 점검용: Y-5~ 주요사항보고·발행공시 중 증자·분할·합병 관련 제목."""
    hits = set()
    for ty in ("B", "C"):
        d = _cached("list.json", {"corp_code": corp_code, "bgn_de": f"{base - 5}0101",
                                  "end_de": date.today().strftime("%Y%m%d"), "pblntf_ty": ty, "page_count": 100},
                    f"{corp_code}_list_{ty}_{base}.json")
        for r in d.get("list") or []:
            nm = re.sub(r"\s+", " ", r.get("report_nm", "")).strip()
            if DILUTION_PAT.search(nm) and "종속회사" not in nm and "자회사" not in nm:
                hits.add((r.get("rcept_dt"), nm))
    return sorted(hits)


def screen(stocks: list, base: int, ov: dict, workers: int = 6, log=print) -> dict:
    cmap = dart_data._load_corpcode_map()
    todo = [s for s in stocks if s["code"] in cmap]
    for s in stocks:
        if s["code"] not in cmap:
            log(f"⚠️ {s['code']} {s.get('name', '')}: DART corp_code 없음 — 제외")
    fin_ov, nonfin_ov = set(ov.get("financials", [])), set(ov.get("nonfinancials", []))

    def one(s):
        cc = cmap[s["code"]]["corp_code"]
        comp = _cached("company.json", {"corp_code": cc}, f"{s['code']}_company.json")
        fin = s["code"] in fin_ov or (s["code"] not in nonfin_ov
                                      and is_financial(comp.get("induty_code"), comp.get("corp_name")))
        collect(s["code"], cc, base, fin)
        return s["code"], fin

    fin_map = {}
    with ThreadPoolExecutor(workers) as ex:
        for i, (code, fin) in enumerate(ex.map(one, todo), 1):
            fin_map[code] = fin
            if i % 20 == 0:
                log(f"  수집 {i}/{len(todo)}")
    collect_multi([cmap[s["code"]]["corp_code"] for s in todo], base)

    usd_years = set()
    reports_by = {}
    for s in todo:
        reps = []
        for ry in sorted(set(report_years(base)) | {base - 2}, reverse=True):
            for fs in ("CFS", "OFS"):
                d = _load(f"{s['code']}_{ry}_{fs}.json")
                if d:
                    cur = (d["list"][0].get("currency") if d.get("list") else "KRW") or "KRW"
                    if cur != "KRW":
                        usd_years |= {ry, ry - 1, ry - 2}
                    reps.append((ry, fs, cur, d["list"]))
                    break
        reports_by[s["code"]] = reps
    fx = fred_usdkrw(usd_years) if usd_years else {}

    out = {}
    for s in todo:
        code = s["code"]
        data, basis, fx_missing = merge_reports(reports_by[code], _multi_rows(code, base), fx)
        sh = [total_shares((_load(f"{code}_{y}_shares.json") or {}).get("list")) for y in (base - 5, base)]
        m = compute_metrics(data, base, sh[0], sh[1])
        vo = ov.get("verdict_override", {}).get(code)
        if fx_missing and not vo:
            vo = ["판정 보류", f"외화 표시 재무({fx_missing}) 환산 환율 없음(FRED_API_KEY 필요)"]
        j = judge(m, financial=fin_map[code], young=code in set(ov.get("listed_under10", [])),
                  costco_type=code in set(ov.get("costco_type", [])),
                  dilution_ok=ov.get("dilution_ok", {}).get(code),
                  cell_override=ov.get("cell_override", {}).get(code), verdict_override=vo)
        if j["cells"][7]["s"] == "fail":
            j["dilution_disclosures"] = dilution_disclosures(cmap[code]["corp_code"], base)
        j.update(code=code, name=s.get("name") or cmap[code]["corp_name"], mcap_eok=s.get("mcap_eok"),
                 financial=fin_map[code], basis=basis, metrics=m)
        out[code] = j
    return out


SYM = {"pass": "✅", "fail": "❌", "warn": "⚠️", "na": "❔", "skip": "—", "exempt": "⚠️→✅", "adj": "⚠️→✅"}


def render(result: dict) -> str:
    lines = ["| 기업 (코드) | ①ROE | ②FCF | ③이자보상 | ④매출총이익률 | ⑤OCF/NI | ⑥순이익률 | ⑦희석 | 결과 |",
             "|---|---|---|---|---|---|---|---|---|"]
    order = {"통과": 0, "면제 통과": 1, "판정 보류": 2, "배제": 3}
    for j in sorted(result.values(), key=lambda j: (order.get(j["verdict"], 9), -(j.get("mcap_eok") or 0))):
        cells = " | ".join("—" if j["cells"][k]["s"] == "skip" else f"{SYM[j['cells'][k]['s']]} {j['cells'][k]['t']}"
                           for k in range(1, 8))
        extra = "".join(f" ({x})" for x in j["exempt"]) + "".join(f" [{f}]" for f in j["flags"])
        lines.append(f"| {j['name']} ({j['code']}) | {cells} | **{j['verdict']}**{extra} |")
    c = {}
    for j in result.values():
        c[j["verdict"]] = c.get(j["verdict"], 0) + 1
    n = len(result)
    passed = c.get("통과", 0) + c.get("면제 통과", 0)
    lines += ["", f"통과 {c.get('통과', 0)} · 면제 통과 {c.get('면제 통과', 0)} · 판정 보류 {c.get('판정 보류', 0)} · "
              f"배제 {c.get('배제', 0)} — 통과율 {passed}/{n} = {passed / n * 100:.1f}%" if n else ""]
    dil = [j for j in result.values() if j.get("dilution_disclosures")]
    if dil:
        lines += ["", "⑦ 희석 20% 초과 — 관련 공시(분할·무상증자·합병이면 overrides dilution_ok로 통과 처리):"]
        for j in dil:
            lines.append(f"- {j['name']} ({j['code']}) {j['cells'][7]['t']}: " +
                         "; ".join(f"{d} {t}" for d, t in j["dilution_disclosures"][:8]))
    return "\n".join(lines)


def default_base_year(today: date = None) -> int:
    """사업보고서는 3월 말까지 나오므로 4월부터 직전 연도, 그 전엔 전전 연도."""
    today = today or date.today()
    return today.year - 1 if today.month >= 4 else today.year - 2


def main():
    global _REFRESH
    p = argparse.ArgumentParser(description="한국 상장사 부실기업 스크리닝(7지표, DART 원본).")
    p.add_argument("codes", nargs="*", help="종목코드 6자리(여러 개)")
    p.add_argument("--index", default="", help="네이버 증권 지수 코드(예: KPI200)")
    p.add_argument("--year", type=int, default=None, help="기준 사업연도(기본: 직전 공시 연도)")
    p.add_argument("--overrides", default="", help="수작업 판단 JSON 경로")
    p.add_argument("--json", default="", help="판정 전체를 저장할 JSON 경로")
    p.add_argument("--workers", type=int, default=6, help="동시 요청 수(기본 6)")
    p.add_argument("--refresh", action="store_true", help="캐시 무시하고 다시 받기")
    a = p.parse_args()
    _REFRESH = a.refresh
    if not a.codes and not a.index:
        p.error("종목코드 또는 --index 가 필요합니다")
    try:
        stocks = fetch_index(a.index) if a.index else []
        stocks += [{"code": c.zfill(6), "name": ""} for c in a.codes]
        ov = {}
        if a.overrides:
            with open(a.overrides, encoding="utf-8") as f:
                ov = json.load(f)
        base = a.year or default_base_year()
        print(f"기준 사업연도 {base} · 대상 {len(stocks)}개 · DART 수집 중(캐시 {CACHE})", file=sys.stderr)
        result = screen(stocks, base, ov, a.workers, log=lambda s: print(s, file=sys.stderr))
    except (ConnectionError, RuntimeError) as e:
        dart_data._die(f"❌ {e}")
    print(render(result))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1, default=str)
        print(f"\nJSON 저장: {a.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
