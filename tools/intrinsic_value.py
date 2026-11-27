#!/usr/bin/env python3
"""내재가치 표준 산식 — 유형을 자동 분류하고 DART·SEC 원본으로 비관·중립·낙관 3개 시나리오와 라벨 범위를 계산한다. stdlib만.

설계: research/내재가치-표준화-계획.md. 기준값(할인율·PER·영구성장률)은 외부 근거로 정한 값이며 매수 종목 수에
맞춰 바꾸지 않는다. 역할: 리포트 라벨 범위를 대체하지 않는 **교차 검증 기준선**이다(분석가 범위가 공식과 ±50% 넘게
다르면 리포트에 괴리 근거를 쓴다). 대체 여부는 원장 정산이 쌓인 뒤 데이터로 정한다.

유형(자동 분류, 순서대로):
  C 금융        DART 업종코드·SEC SIC 6000~6799                     → 정당 PBR = (ROE − g) / (COE − g) × BPS
  B 경기순환    10년 영업이익 최대 하락 ≥ 50% 또는 흑자→적자 전환     → 정상 이익 × PER + 순현금
                (mos_inputs 와 같은 하락률: 회계 조정·초기 적자 제외 반영)
  E 가정 의존형 최근 5년 평균 오너어닝스(영업CF − CapEx − 주식보상) ≤ 0 → 자동 계산하지 않음(수기 가정 필요)
  A 일반        그 밖                                                → 2단계 오너어닝스 DCF + 순현금

시나리오(비관 / 중립 / 낙관):
  A  1단계(5년) 성장 = min(0, CAGR) / CAGR × 0.5 / min(max(CAGR, 0), 15%)  (CAGR: 최대 10년 매출 연평균 성장률)
     영구성장 1% / 2% / 3%, 할인율 r = USD 9% · KRW 10% · 그 밖 10%
  B  영업이익률 = 10년 하위 3개 해 평균 / 10년 평균 / 상위 3개 해 평균, × 현재 매출 × (1 − 세율),
     PER = 시장 장기 PER × 0.6 / 0.8 / 1.0 (미국 16 → 9.6/12.8/16, 한국 10 → 6/8/10)
  C  ROE = 10년 하위 3개 해 평균 / 10년 평균 / 최근 3개 해 평균, COE = USD 9% · KRW 10%, g = 2%
라벨 범위(규칙 (나)) = (비관 + 중립) / 2 ~ (중립 + 낙관) / 2

순현금 = 현금및현금성자산 + 단기금융상품(단기투자) − 차입금·사채(리스부채 제외), 같은 결산일 값.
주식수: 한국 = 유통주식수(발행 − 자기주식, 보통+우선), 미국 = 최근 연도 희석 가중평균 주식수.
재무제표 통화와 거래 통화가 다르면(ADR 등) 주당가치를 비교할 수 없으므로 '통화 불일치'로 표시만 한다.

사용법:
    python3 tools/intrinsic_value.py calc 000270 --as-of 2026-11-20
    python3 tools/intrinsic_value.py calc KO --as-of 2026-11-21 --json
    python3 tools/intrinsic_value.py ledger                     # 원장 종목별 최신 → 공식 vs 분석가 범위 CSV

종료 코드: 0 정상 / 3 데이터 없음 / 4 출처 장애
필요 Python >= 3.8, 외부 종속성 없음. 한국은 DART_API_KEY 필요.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _us_common import NoDataError, run  # noqa: E402
import mos_inputs as mi  # noqa: E402

DISCOUNT = {"USD": 9.0, "KRW": 10.0}
DISCOUNT_DEFAULT = 10.0
TERMINAL = (1.0, 2.0, 3.0)
GROWTH_CAP = 15.0
STAGE1_YEARS = 5
# 경기순환 PER = 시장 장기 PER × (0.6, 0.8, 1.0). 시장 장기 PER(외부 근거, 2026-11 확인):
#   미국 16 — S&P500 장기 평균 후행 PER 16~18(Advisor Perspectives 16.2, Seeking Alpha 16.8, Kiplinger 17.4)
#   한국 10 — 코스피 12개월 선행 PER 최근 10년 평균 10.25, 분포 8.6~12.2(블루밍비트·신한투자증권)
MARKET_PE = {"US": 16.0, "KR": 10.0}
CYCLE_FACTORS = (0.6, 0.8, 1.0)


def cycle_pe(market: str) -> tuple:
    base = MARKET_PE.get(market, MARKET_PE["KR"])
    return tuple(round(base * f, 2) for f in CYCLE_FACTORS)
TAX = {"USD": 21.0, "KRW": 22.0}
TAX_DEFAULT = 22.0
FIN_G = 2.0
CYCLE_DD = 50.0
SCENARIOS = ("비관", "중립", "낙관")
TYPE_NAME = {"A": "A 일반(2단계 오너어닝스 DCF)", "B": "B 경기순환(정상화 이익 × PER)",
             "C": "C 금융(정당 PBR)", "E": "E 가정 의존형(수기 가정 필요)"}
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IV_CSV = os.path.join(_ROOT, "reports", "decision-iv.csv")
IV_FIELDS = ["id", "기록일", "종목", "티커", "통화", "판단", "기록시점가", "분석가하단", "분석가상단", "분석가중앙",
             "유형", "비관", "중립", "낙관", "공식하단", "공식상단", "공식중앙", "공식/분석가", "U_v공식",
             "U_e", "L", "요구안전마진공식", "현재안전마진공식", "상태공식", "주식수", "순현금", "비고", "계산일"]


# ---------------------------------------------------------------------------
# 순수 함수(테스트 대상)
# ---------------------------------------------------------------------------

def cagr(series: dict, max_years: int = 10):
    """{연도: 값} → 최대 max_years 개 해의 연평균 성장률(%). 양 끝이 양수이고 5개 해 이상일 때만."""
    ys = sorted(y for y, v in series.items() if v is not None)[-max_years:]
    if len(ys) < 5 or series[ys[0]] <= 0 or series[ys[-1]] <= 0:
        return None
    n = ys[-1] - ys[0]
    return ((series[ys[-1]] / series[ys[0]]) ** (1 / n) - 1) * 100


def growth_scenarios(g: float) -> tuple:
    """매출 CAGR(%) → 1단계 성장률 (비관, 중립, 낙관)."""
    return (min(0.0, g), g * 0.5, min(max(g, 0.0), GROWTH_CAP))


def dcf_value(oe0: float, g1: float, g2: float, r: float, years: int = STAGE1_YEARS) -> float:
    """2단계 DCF: 1단계 years 년 g1 성장, 이후 g2 영구성장, 할인율 r (모두 %)."""
    g1, g2, r = g1 / 100, g2 / 100, r / 100
    if r <= g2:
        raise ValueError("할인율이 영구성장률보다 커야 합니다.")
    pv, cf = 0.0, oe0
    for t in range(1, years + 1):
        cf *= 1 + g1
        pv += cf / (1 + r) ** t
    tv = cf * (1 + g2) / (r - g2)
    return pv + tv / (1 + r) ** years


def margin_scenarios(margins: list) -> tuple:
    """영업이익률 목록(최근 10개 해) → (하위 3개 평균, 전체 평균, 상위 3개 평균)."""
    m = sorted(margins)
    k = min(3, len(m))
    return (sum(m[:k]) / k, sum(m) / len(m), sum(m[-k:]) / k)


def roe_series(ni: dict, eq: dict) -> dict:
    """연도별 ROE(%) = 순이익 / 평균 자본(전년·당년). 전년 자본이 없으면 기말 자본."""
    out = {}
    for y in sorted(ni):
        e1, e0 = eq.get(y), eq.get(y - 1)
        base = (e1 + e0) / 2 if e1 and e0 else e1
        if ni[y] is not None and base and base > 0:
            out[y] = ni[y] / base * 100
    return out


def justified_pbr(roe: float, coe: float, g: float = FIN_G) -> float:
    return max((roe - g) / (coe - g), 0.0)


def label_range(bear: float, mid: float, bull: float) -> tuple:
    """규칙 (나): (비관+중립)/2 ~ (중립+낙관)/2."""
    return ((bear + mid) / 2, (mid + bull) / 2)


def classify(financial: bool, dd: dict, oe5) -> str:
    if financial:
        return "C"
    if dd.get("하락률") is not None and dd["하락률"] >= CYCLE_DD and dd.get("연도수", 0) >= mi.MIN_YEARS:
        return "B"
    if oe5 is None or oe5 <= 0:
        return "E"
    return "A"


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

_KR_DEBT = re.compile(r"차입금|사채|유동성장기부채")
_KR_SKIP = re.compile(r"리스|이자|충당|합계|총계|채권|미지급|선수|예수|파생")


def kr_extras(got: dict) -> dict:
    """원문 재무상태표 → 순현금·주식수. 최근 보고서의 당기말."""
    import quality_screen_kr as kr
    out = {"cash": None, "debt": None, "shares": None, "bs_year": None, "shares_note": ""}
    for ry, _, cur, items in sorted(got["reps"], key=lambda r: -r[0]):
        if cur and cur != "KRW":
            continue
        bs = [it for it in items if it.get("sj_div") == "BS"]
        if not bs:
            continue
        cash = sum(kr.num(it.get("thstrm_amount")) or 0 for it in bs
                   if it.get("account_id") in ("ifrs-full_CashAndCashEquivalents",
                                               "ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents")
                   or (it.get("account_nm") or "").replace(" ", "") in ("단기금융상품",))
        debt = sum(kr.num(it.get("thstrm_amount")) or 0 for it in bs
                   if _KR_DEBT.search(it.get("account_nm") or "") and not _KR_SKIP.search(it.get("account_nm") or ""))
        out.update(cash=cash, debt=debt, bs_year=ry)
        break
    sh = kr._load(f"{got['code']}_{got['base']}_shares.json")
    if sh:
        rows = sh.get("list") or []
        tot = next((r for r in rows if r.get("se") == "합계"), None)
        vals = [kr.num(tot.get("distb_stock_co"))] if tot else [kr.num(r.get("distb_stock_co")) for r in rows
                                                               if r.get("se") in ("보통주", "우선주")]
        vals = [v for v in vals if v]
        if vals:
            out["shares"] = sum(vals)
            out["shares_note"] = "유통주식(보통+우선)"
    return out


def us_extras(got: dict, as_of: str) -> dict:
    import quality_screen_us as us
    import sec_edgar_data as sec
    g = got["facts"]

    def inst(tags):
        v, _ = sec.values_as_of(g, tags, as_of, us.INSTANT, us.FORMS)
        return {k[0]: x for k, x in v.items()}

    cash = inst(("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                 "Cash"))
    out = {"cash": None, "debt": None, "shares": None, "bs_year": None, "shares_note": "희석 가중평균"}
    if cash:
        end = max(cash)
        sti = inst(("ShortTermInvestments", "MarketableSecuritiesCurrent",
                    "AvailableForSaleSecuritiesDebtSecuritiesCurrent")).get(end, 0)
        ltd = inst(("LongTermDebt", "LongTermDebtAndCapitalLeaseObligations")).get(end)
        if ltd is None:
            ltd = (inst(("LongTermDebtNoncurrent",)).get(end, 0) + inst(("LongTermDebtCurrent", "DebtCurrent")).get(end, 0))
        std = inst(("ShortTermBorrowings",)).get(end, 0) + inst(("CommercialPaper",)).get(end, 0)
        out.update(cash=cash[end] + sti, debt=ltd + std, bs_year=int(end[:4]))
    shs, _ = sec.values_as_of(g, ("WeightedAverageNumberOfDilutedSharesOutstanding",), as_of, us.ANNUAL, us.FORMS)
    if shs:
        out["shares"] = shs[max(shs)]
    sbc, _ = sec.values_as_of(g, ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"), as_of,
                              us.ANNUAL, us.FORMS)
    out["sbc"] = {int(k[0][:4]): v for k, v in sbc.items()}
    return out


def collect(ticker: str, as_of: str) -> dict:
    t = mi.SEC_ALIASES.get(ticker.upper(), ticker)
    mk = mi.market_of(t)
    if mk == "OTHER":
        raise NoDataError(f"{ticker}: 재무 원본 미지원 시장")
    got = mi.fetch_kr(t, as_of) if mk == "KR" else mi.fetch_us(t, as_of)
    ex = kr_extras(got) if mk == "KR" else us_extras(got, as_of)
    cur = "KRW" if mk == "KR" else got.get("currency", "USD")
    return {"data": got["data"], "financial": got["financial"], "currency": cur, "extras": ex,
            "source": got["source"], "market": mk}


# ---------------------------------------------------------------------------
# 평가
# ---------------------------------------------------------------------------

def evaluate(ticker: str, as_of: str, trade_currency: str = "", mos_info=None) -> dict:
    """→ {유형, 시나리오 3개(주당), 라벨 범위, 근거, 경고}. mos_info 는 mos_inputs.compute 결과(재사용)."""
    as_of = as_of or date.today().isoformat()
    c = collect(ticker, as_of)
    mos_info = mos_info or mi.compute(ticker, as_of)
    data, ex, cur = c["data"], c["extras"], c["currency"]
    ys = sorted(data)[-10:]
    warn = []
    sbc = ex.get("sbc") or {}
    oe = {}
    for y in ys:
        r = data[y]
        if r.get("ocf") is None:
            continue
        capex = abs(r.get("capex_ppe") or 0) + abs(r.get("capex_int") or 0)
        oe[y] = r["ocf"] - capex - abs(sbc.get(y, 0))
    last5 = [oe[y] for y in sorted(oe)[-5:]]
    oe5 = sum(last5) / len(last5) if len(last5) >= 3 else None
    typ = classify(c["financial"], mos_info["drawdown"], oe5)
    shares = ex.get("shares")
    net_cash = (ex["cash"] or 0) - (ex["debt"] or 0) if ex.get("cash") is not None else 0.0
    if ex.get("cash") is None and typ in "AB":
        warn.append("현금·차입금 미확보 → 순현금 0으로 계산")
    out = {"유형": typ, "유형명": TYPE_NAME[typ], "통화": cur, "주식수": shares, "순현금": net_cash,
           "근거": {}, "경고": warn, "시나리오": None, "범위": None, "source": c["source"]}
    if trade_currency and trade_currency != cur:
        warn.append(f"재무 통화 {cur} ≠ 거래 통화 {trade_currency} — 주당가치 비교 불가(ADR 비율·환율 수기 필요)")
        out["통화불일치"] = True
    if typ == "E" or not shares:
        if not shares:
            warn.append("주식수 미확보")
        return out
    if typ == "A":
        rev = {y: data[y].get("rev") for y in ys}
        g = cagr(rev)
        if g is None:
            warn.append("매출 CAGR 산정 불가 → 0%")
            g = 0.0
        r = DISCOUNT.get(cur, DISCOUNT_DEFAULT)
        gs = growth_scenarios(g)
        vals = [(dcf_value(oe5, g1, g2, r) + net_cash) / shares for g1, g2 in zip(gs, TERMINAL)]
        out["근거"] = {"OE5": oe5, "매출CAGR": round(g, 2), "1단계성장": [round(x, 2) for x in gs],
                     "영구성장": list(TERMINAL), "할인율": r}
    elif typ == "B":
        margins = [data[y]["op"] / data[y]["rev"] * 100 for y in ys if data[y].get("op") is not None
                   and data[y].get("rev")]
        last_rev = next((data[y]["rev"] for y in reversed(ys) if data[y].get("rev")), None)
        if len(margins) < 5 or not last_rev:
            warn.append("영업이익률·매출 이력 부족")
            return out
        ms = margin_scenarios(margins)
        if ms[1] <= 0:  # 10년 평균 영업이익률이 적자면 정상화할 이익이 없다 → 가정 의존형
            out.update(유형="E", 유형명=TYPE_NAME["E"])
            warn.append(f"10년 평균 영업이익률 {ms[1]:.1f}% ≤ 0 → E(수기 가정)")
            return out
        tax = TAX.get(cur, TAX_DEFAULT)
        pes = cycle_pe(c["market"])
        vals = [(last_rev * m / 100 * (1 - tax / 100) * pe + net_cash) / shares for m, pe in zip(ms, pes)]
        out["근거"] = {"영업이익률": [round(m, 2) for m in ms], "매출": last_rev, "PER": list(pes), "세율": tax}
    else:  # C
        ni = {y: data[y].get("ni_own") for y in ys}
        eq = {y: data[y].get("eq_own") for y in sorted(data)}
        roe = roe_series(ni, eq)
        if len(roe) < 5:
            warn.append("ROE 이력 부족")
            return out
        rs = sorted(roe.values())
        k = 3
        last3 = [roe[y] for y in sorted(roe)[-3:]]
        scen = (sum(rs[:k]) / k, sum(rs) / len(rs), sum(last3) / len(last3))
        coe = DISCOUNT.get(cur, DISCOUNT_DEFAULT)
        bps = eq[max(eq)] / shares
        vals = [justified_pbr(x, coe) * bps for x in scen]
        out["근거"] = {"ROE": [round(x, 2) for x in scen], "COE": coe, "g": FIN_G, "BPS": bps}
    bear, mid, bull = sorted(vals)
    out["시나리오"] = {"비관": bear, "중립": mid, "낙관": bull}
    out["범위"] = label_range(bear, mid, bull)
    return out


def fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:,.2f}"


def formula_line(res: dict) -> str:
    if not res.get("시나리오"):
        return f"**내재가치 산식**: {res['유형명']} | 자동 계산 불가({'; '.join(res['경고']) or '수기 가정 필요'})"
    s, (lo, hi) = res["시나리오"], res["범위"]
    return (f"**내재가치 산식**: {res['유형명']} | 비관 {fmt(s['비관'])} / 중립 {fmt(s['중립'])} / 낙관 {fmt(s['낙관'])} "
            f"| 범위 {fmt(lo)}~{fmt(hi)} {res['통화']}")


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------

def cmd_calc(a):
    res = evaluate(a.ticker, a.as_of, a.trade_currency)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return
    print(formula_line(res))
    print(f"근거: {json.dumps(res['근거'], ensure_ascii=False, default=str)}")
    print(f"순현금 {fmt(res['순현금'])} {res['통화']} · 주식수 {fmt(res['주식수'] or 0)}")
    for w in res["경고"]:
        print(f"⚠️ {w}")


def ledger_compare(ledger_path: str, today_s: str = "", eval_fn=evaluate, mos_rows=None) -> list:
    import decision_ledger as dl
    rows = dl._read(ledger_path)
    latest = {}
    for r in rows:
        if r["종목"] not in latest or r["기록일"] >= latest[r["종목"]]["기록일"]:
            latest[r["종목"]] = r
    mos = {}
    for m in mos_rows or []:
        mos[m["id"]] = m
    out = []
    for r in sorted(latest.values(), key=lambda r: r["기록일"]):
        row = {k: r.get(k, "") for k in ("id", "기록일", "종목", "티커", "통화", "판단", "기록시점가")}
        row["계산일"] = today_s or date.today().isoformat()
        try:
            lo, hi = float(r["내재가치하단"]), float(r["내재가치상단"])
            row.update(분석가하단=lo, 분석가상단=hi, 분석가중앙=(lo + hi) / 2)
        except ValueError:
            lo = hi = None
        try:
            res = eval_fn(r["티커"], r["기록일"], r["통화"])
        except Exception as e:  # noqa: BLE001
            row.update(유형="-", 비고=f"계산 실패: {str(e)[:100]}")
            out.append(row)
            continue
        row.update(유형=res["유형"], 주식수=res["주식수"] or "", 순현금=res["순현금"], 비고="; ".join(res["경고"]))
        m = mos.get(r["id"], {})
        if res.get("시나리오") and not res.get("통화불일치"):
            s, (flo, fhi) = res["시나리오"], res["범위"]
            fmid = (flo + fhi) / 2
            row.update(비관=round(s["비관"], 2), 중립=round(s["중립"], 2), 낙관=round(s["낙관"], 2),
                       공식하단=round(flo, 2), 공식상단=round(fhi, 2), 공식중앙=round(fmid, 2))
            if lo:
                row["공식/분석가"] = round(fmid / ((lo + hi) / 2), 3)
            if fmid > 0:
                uv = mi.u_v_from(flo, fhi)
                try:
                    ue, lp = float(m.get("U_e")), float(m.get("L"))
                    req = mi.required_mos(uv, ue, lp)
                    row.update(U_v공식=uv, U_e=ue, L=lp, 요구안전마진공식=req)
                    price = float(r["기록시점가"])
                    cur_m = round((1 - price / fmid) * 100, 1)
                    row["현재안전마진공식"] = cur_m
                    row["상태공식"] = ("A 요구 충족" if cur_m >= req else "B 1차 도달" if cur_m >= req - 10
                                   else "C 가격 대기")
                except (TypeError, ValueError):
                    pass
        out.append(row)
    return out


def cmd_ledger(a):
    import decision_ledger as dl
    mos_rows = list(csv.DictReader(open(mi.MOS_CSV, encoding="utf-8"))) if os.path.exists(mi.MOS_CSV) else []
    rows = ledger_compare(a.ledger or dl.LEDGER, mos_rows=mos_rows)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=IV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in IV_FIELDS})
    from collections import Counter
    print(f"{len(rows)}종목 → {a.out}")
    print("  유형: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.get('유형', '-') for r in rows).items())))
    print("  상태(공식): " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.get('상태공식', '-') for r in rows).items())))


def main():
    p = argparse.ArgumentParser(description="내재가치 표준 산식(유형 분류·3개 시나리오·라벨 범위).")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calc")
    c.add_argument("ticker")
    c.add_argument("--as-of", default="")
    c.add_argument("--trade-currency", default="", help="거래 통화(재무 통화와 다르면 비교 불가 표시)")
    c.add_argument("--json", action="store_true")
    lg = sub.add_parser("ledger", help="원장 종목별 최신 → 공식 vs 분석가 범위")
    lg.add_argument("--ledger", default="")
    lg.add_argument("--out", default=IV_CSV)
    a = p.parse_args()
    (cmd_calc if a.cmd == "calc" else cmd_ledger)(a)


if __name__ == "__main__":
    run(main)
