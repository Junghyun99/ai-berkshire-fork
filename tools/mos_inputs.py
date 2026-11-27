#!/usr/bin/env python3
"""요구 안전마진 입력 계산 — 종목의 재무 원본(DART·SEC)으로 U_e(이익 변동)·L(재무 위험)을 계산한다. stdlib만.

요구 안전마진(investment-team SKILL.md 7단계 규칙 8, 세 리서치 스킬 공통):

    M = clip( 10% + max(U_v, U_e) + L , 15%, 45% )
    분할 매수: 1차 = 내재가치 중앙 × (1 − (M − 10%)), 2차 = 중앙 × (1 − M), 3차 = 중앙 × (1 − (M + 10%))

  U_v  추정 오차 = (내재가치 상단 − 하단) / 2 / 중앙. 라벨 줄에서 계산(분석가가 스스로 본 불확실성)
  U_e  이익 변동 = 최근 10개 회계연도 이익의 고점 대비 최대 하락률 × 0.3, 상한 30%.
       이익: 비금융은 영업이익(법인세 일회성·평가손익 같은 영업 외 항목을 걸러 사이클만 본다),
       금융(은행·보험·증권·지주)은 지배주주 순이익(영업이익 정의가 업종마다 달라서).
       기간 중 한 해라도 0 이하(적자)면 하락률 100%. 연간 이익이 5개 해 미만이면 이력 부족으로 U_e 30%.
       재무 원본을 받을 수 없는 시장(일본 등)도 U_e 30% — 다른 출처로 계산했으면 --u-e 로 직접 넣는다.
  L    재무 위험 = 최근 연도 이자보상배율(영업이익 / 이자비용) 8배 이상 0, 3~8배 +5%p, 3배 미만·영업적자 +10%p.
       이자비용이 없으면 0. 금융업은 이자가 영업 원가라 0(자본비율 위험은 리포트 판단으로 +5%p 가능).
  max(U_v, U_e) 인 이유: 정직하게 넓게 잡은 범위에는 이익 변동이 이미 들어 있다. 둘을 더하면 같은 위험을
  두 번 깎는다. U_e 는 범위가 비정상적으로 좁을 때의 바닥 역할이다.

사용법:
    python3 tools/mos_inputs.py calc 000270 --as-of 2026-11-20 --iv-low 95000 --iv-high 130000 --price 88200
    python3 tools/mos_inputs.py calc KO                                  # U_e·L 만
    python3 tools/mos_inputs.py calc 6871.T --u-e 18                     # 원본 없는 시장: 다른 출처로 계산한 U_e
    python3 tools/mos_inputs.py ledger                                   # 판단 원장 전부 → reports/decision-mos.csv

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

BASE_PCT = 10.0
UE_FACTOR = 0.3
UE_CAP = 30.0
MOS_FLOOR, MOS_CAP = 15.0, 45.0
TRANCHE_OFFSETS = (-10.0, 0.0, 10.0)
MIN_YEARS = 5
COVERAGE_STEPS = ((8.0, 0.0), (3.0, 5.0))  # 이자보상배율 ≥ 8 → 0, ≥ 3 → 5, 그 밖 → 10
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOS_CSV = os.path.join(_ROOT, "reports", "decision-mos.csv")
MOS_FIELDS = ["id", "기록일", "종목", "티커", "통화", "판단", "기록시점가", "내재가치하단", "내재가치상단",
              "U_v", "이익지표", "최대하락", "하락구간", "U_e", "이자보상배율", "L", "요구안전마진",
              "1차", "2차", "3차", "현재안전마진", "상태", "비고", "계산일"]


# ---------------------------------------------------------------------------
# 순수 함수(테스트 대상)
# ---------------------------------------------------------------------------

def earnings_drawdown(series: dict) -> dict:
    """{연도: 이익} → {하락률, 고점연도, 저점연도, 연도수}. 최근 10개 해만. 0 이하인 해가 있으면 100%."""
    ys = sorted(y for y, v in series.items() if v is not None)[-10:]
    out = {"하락률": None, "고점연도": None, "저점연도": None, "연도수": len(ys)}
    if not ys:
        return out
    loss = [y for y in ys if series[y] <= 0]
    if loss:
        out.update(하락률=100.0, 저점연도=loss[0])
        prior = [y for y in ys if y < loss[0] and series[y] > 0]
        out["고점연도"] = max(prior, key=lambda y: series[y]) if prior else None
        return out
    peak_y, best = ys[0], (0.0, None, None)
    for y in ys[1:]:
        if series[y] > series[peak_y]:
            peak_y = y
            continue
        dd = (series[peak_y] - series[y]) / series[peak_y] * 100
        if dd > best[0]:
            best = (dd, peak_y, y)
    out.update(하락률=round(best[0], 1), 고점연도=best[1], 저점연도=best[2])
    return out


def u_e_from(dd: dict) -> float:
    if dd["하락률"] is None or dd["연도수"] < MIN_YEARS:
        return UE_CAP
    return round(min(UE_FACTOR * dd["하락률"], UE_CAP), 1)


def leverage_penalty(op, interest, financial: bool):
    """→ (이자보상배율 또는 None, L). 금융업은 0."""
    if financial:
        return None, 0.0
    interest = abs(interest or 0)
    if op is None:
        return None, 10.0
    if op <= 0:
        return round(op / interest, 2) if interest else None, 10.0
    if not interest:
        return None, 0.0
    cov = op / interest
    for th, pen in COVERAGE_STEPS:
        if cov >= th:
            return round(cov, 2), pen
    return round(cov, 2), 10.0


def u_v_from(iv_low: float, iv_high: float) -> float:
    mid = (iv_low + iv_high) / 2
    return round((iv_high - iv_low) / 2 / mid * 100, 1)


def required_mos(u_v: float, u_e: float, l_pen: float) -> float:
    return round(min(max(BASE_PCT + max(u_v, u_e) + l_pen, MOS_FLOOR), MOS_CAP), 1)


def tranche_mos(m: float) -> tuple:
    return tuple(round(m + o, 1) for o in TRANCHE_OFFSETS)


def margin_line(price: float, iv_low: float, iv_high: float, u_e: float, l_pen: float, unit: str = "") -> str:
    mid = (iv_low + iv_high) / 2
    uv = u_v_from(iv_low, iv_high)
    m = required_mos(uv, u_e, l_pen)
    f = (lambda x: f"{x:,.0f}") if mid >= 1000 else (lambda x: f"{x:,.2f}")
    return (f"**안전마진**: 기준가 {f(price)}{unit} · 중앙 {f(mid)}{unit} → {(1 - price / mid) * 100:.1f}% | "
            f"**요구 안전마진**: 10 + max(U_v {uv:g}, U_e {u_e:g}) + L {l_pen:g} = {m:g}%")


def inputs_line(info: dict) -> str:
    dd = info["drawdown"]
    if info.get("manual_u_e"):
        ev = f"**이익 변동**: 직접 계산 U_e {info['u_e']:g}% ({info.get('note') or '출처 기재'})"
    elif dd["하락률"] is None or dd["연도수"] < MIN_YEARS:
        ev = f"**이익 변동**: 이력 부족·데이터 미확보({dd['연도수']}개 해) → U_e {info['u_e']:g}%"
    else:
        span = f"{dd['고점연도']}→{dd['저점연도']}" if dd["저점연도"] else "하락 없음"
        ev = (f"**이익 변동**: {info['metric']} 최대 하락 {dd['하락률']:g}% ({span}, {dd['연도수']}개 해, "
              f"{info['source']}) → U_e {info['u_e']:g}%")
    if info["financial"]:
        lv = f"**재무 위험**: 금융업 → L {info['L']:g}"
    elif info.get("manual_u_e"):
        lv = f"**재무 위험**: 직접 판정 → L {info['L']:g}"
    elif info["coverage"] is None:
        lv = f"**재무 위험**: 이자보상배율 산정 불가({'영업적자' if info['L'] == 10 else '이자비용 없음'}) → L {info['L']:g}"
    else:
        lv = f"**재무 위험**: 이자보상배율 {info['coverage']:g}배({info['cov_year']}) → L {info['L']:g}"
    return f"{ev} | {lv}"


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------

# 본국 상장 티커 → SEC 에 20-F 를 내는 ADR 티커(재무 원본을 SEC 에서 받는다)
SEC_ALIASES = {"2330.TW": "TSM"}


def market_of(ticker: str) -> str:
    t = ticker.upper()
    if re.fullmatch(r"\d{6}(\.K[SQ])?", t):
        return "KR"
    if re.search(r"\.(T|TW|HK|SS|SZ)$", t):
        return "OTHER"
    return "US"


def _base_year(as_of: str) -> int:
    d = date.fromisoformat(as_of)
    return d.year - 1 if d.month >= 4 else d.year - 2  # 사업보고서는 3월 말까지 제출


def fetch_kr(code: str, as_of: str) -> dict:
    import dart_data
    import quality_screen_kr as kr
    code = code[:6]
    cmap = dart_data._load_corpcode_map()
    if code not in cmap:
        raise NoDataError(f"{code}: DART corp_code 없음")
    cc, base = cmap[code]["corp_code"], _base_year(as_of)
    comp = kr._cached("company.json", {"corp_code": cc}, f"{code}_company.json")
    fin = kr.is_financial(comp.get("induty_code"), comp.get("corp_name"))
    kr.collect(code, cc, base, fin)
    reps, usd = [], set()
    for ry in sorted(set(kr.report_years(base)) | {base - 2}, reverse=True):
        for fs in ("CFS", "OFS"):
            d = kr._load(f"{code}_{ry}_{fs}.json")
            if d:
                cur = (d["list"][0].get("currency") if d.get("list") else "KRW") or "KRW"
                if cur != "KRW":
                    usd |= {ry, ry - 1, ry - 2}
                reps.append((ry, fs, cur, d["list"]))
                break
    data, _, _ = kr.merge_reports(reps, kr._multi_rows(code, base), kr.fred_usdkrw(usd) if usd else {})
    data = {y: r for y, r in data.items() if y <= base}
    return {"data": data, "financial": fin, "source": "DART", "name": comp.get("corp_name", code)}


def _sec_financial(ticker: str) -> bool:
    import sec_edgar_data as sec
    cik, _ = sec.resolve(ticker.replace(".", "-"))
    sub = sec._cached_json(sec._SUBMISSIONS_URL.format(cik=cik), f"sec_sub_CIK{cik}.json")
    try:
        return 6000 <= int(sub.get("sic") or 0) <= 6799
    except ValueError:
        return False


def fetch_us(ticker: str, as_of: str) -> dict:
    import quality_screen_us as us
    g = us.merged_facts(us.load_facts(ticker))
    data, cur = us.annual_data(g, as_of)
    for r in data.values():
        if "ni_own" not in r and "ni" in r:
            r["ni_own"] = r["ni"]
        if "op" not in r and "pretax" in r:
            r["op"] = r["pretax"] + abs(r.get("int_is") or r.get("int_cf") or 0)
    return {"data": data, "financial": _sec_financial(ticker), "source": f"SEC({cur})", "name": ticker}


def compute(ticker: str, as_of: str = "", financial=None, u_e=None, note: str = "", l_pen=None) -> dict:
    """→ {metric, drawdown, u_e, coverage, cov_year, L, financial, source}.
    u_e·l_pen 을 주면 원본 대신 그 값을 쓴다(원본 없는 시장용, note 에 출처)."""
    as_of = as_of or date.today().isoformat()
    ticker = SEC_ALIASES.get(ticker.upper(), ticker)
    mk = market_of(ticker)
    if u_e is not None:
        fin = bool(financial)
        if l_pen not in (None, 0, 5, 10):
            raise SystemExit("❌ --l 은 0, 5, 10 중 하나")
        return {"metric": "-", "drawdown": {"하락률": None, "고점연도": None, "저점연도": None, "연도수": 0},
                "u_e": min(float(u_e), UE_CAP), "manual_u_e": True, "note": note, "coverage": None,
                "cov_year": None, "L": 0.0 if fin else float(l_pen or 0), "financial": fin, "source": "직접 입력"}
    if mk == "OTHER":
        dd = {"하락률": None, "고점연도": None, "저점연도": None, "연도수": 0}
        return {"metric": "-", "drawdown": dd, "u_e": UE_CAP, "coverage": None, "cov_year": None, "L": 0.0,
                "financial": bool(financial), "source": "원본 미지원 시장", "missing": True}
    got = fetch_kr(ticker, as_of) if mk == "KR" else fetch_us(ticker, as_of)
    fin = got["financial"] if financial is None else financial
    key = "ni_own" if fin else "op"
    data = got["data"]
    series = {y: r.get(key) for y, r in data.items() if r.get(key) is not None}
    dd = earnings_drawdown(series)
    last = max(series) if series else None
    r = data.get(last, {}) if last else {}
    cov, pen = leverage_penalty(r.get("op"), r.get("int_is") or r.get("int_cf"), fin)
    return {"metric": "지배순이익" if fin else "영업이익", "drawdown": dd, "u_e": u_e_from(dd), "coverage": cov,
            "cov_year": last, "L": pen, "financial": fin, "source": got["source"],
            "series": {y: series[y] for y in sorted(series)[-10:]}}


def plan_prices(iv_low: float, iv_high: float, m: float) -> list:
    import position_plan as pp
    mid = (iv_low + iv_high) / 2
    return [pp.round_price(mid * (1 - t / 100)) for t in tranche_mos(m)]


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------

def cmd_calc(a):
    info = compute(a.ticker, a.as_of, a.financial, a.u_e, a.note, a.l_pen)
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
        return
    print(f"## 요구 안전마진 입력 — {a.ticker} (기준 {a.as_of or date.today().isoformat()}, {info['source']})\n")
    if info.get("series"):
        print("| 연도 | " + info["metric"] + " |\n|---|---|")
        for y, v in info["series"].items():
            print(f"| {y} | {v:,.0f} |")
        print()
    print(inputs_line(info))
    if info.get("missing"):
        print("\n> ⚠️ 재무 원본을 받을 수 없는 시장이라 U_e 를 상한 30%로 둡니다. 다른 출처로 계산했으면 --u-e 로 넣으세요.")
    if a.iv_low and a.iv_high:
        uv = u_v_from(a.iv_low, a.iv_high)
        m = required_mos(uv, info["u_e"], info["L"])
        print()
        if a.price:
            print(margin_line(a.price, a.iv_low, a.iv_high, info["u_e"], info["L"]))
        else:
            print(f"요구 안전마진 = 10 + max(U_v {uv:g}, U_e {info['u_e']:g}) + L {info['L']:g} = {m:g}%")
        p = plan_prices(a.iv_low, a.iv_high, m)
        print("분할 매수 가격: " + " / ".join(f"{t:g}% {x:,.2f}" for t, x in zip(tranche_mos(m), p)))


def ledger_rows(ledger_path: str, compute_fn=compute, today_s: str = "") -> list:
    import decision_ledger as dl
    today_s = today_s or date.today().isoformat()
    cache, out = {}, []
    for r in dl._read(ledger_path):
        key = (r["티커"], r["기록일"])
        if key not in cache:
            try:
                cache[key] = compute_fn(r["티커"], r["기록일"])
            except Exception as e:  # noqa: BLE001 — 한 종목 실패로 전체를 멈추지 않는다
                cache[key] = {"error": str(e)}
        info = cache[key]
        row = {k: r.get(k, "") for k in ("id", "기록일", "종목", "티커", "통화", "판단", "기록시점가",
                                         "내재가치하단", "내재가치상단")}
        row["계산일"] = today_s
        if "error" in info:
            row.update(상태="계산 실패", 비고=info["error"][:120])
            out.append(row)
            continue
        dd = info["drawdown"]
        row.update(이익지표=info["metric"], 최대하락=dd["하락률"] if dd["하락률"] is not None else "",
                   하락구간=f"{dd['고점연도']}→{dd['저점연도']}" if dd["저점연도"] else "",
                   U_e=info["u_e"], 이자보상배율=info["coverage"] if info["coverage"] is not None else "",
                   L=info["L"], 비고=("이력 부족·데이터 미확보 → U_e 상한" if dd["연도수"] < MIN_YEARS else
                                     ("금융업" if info["financial"] else "")) + f" [{info['source']}]")
        try:
            lo, hi = float(r["내재가치하단"]), float(r["내재가치상단"])
        except ValueError:
            row["상태"] = "내재가치 없음"
            out.append(row)
            continue
        uv = u_v_from(lo, hi)
        m = required_mos(uv, info["u_e"], info["L"])
        p1, p2, p3 = plan_prices(lo, hi, m)
        row.update(U_v=uv, 요구안전마진=m, **{"1차": p1, "2차": p2, "3차": p3})
        try:
            price = float(r["기록시점가"])
        except ValueError:
            row["상태"] = "기록가 없음"
            out.append(row)
            continue
        cur = round((1 - price / ((lo + hi) / 2)) * 100, 1)
        row["현재안전마진"] = cur
        if r["판단"] == "회피":
            row["상태"] = "회피"
        elif cur >= m:
            row["상태"] = "A 요구 충족"
        elif cur >= m - 10:
            row["상태"] = "B 1차 도달"
        else:
            row["상태"] = "C 가격 대기"
        out.append(row)
    return out


def cmd_ledger(a):
    import decision_ledger as dl
    rows = ledger_rows(a.ledger or dl.LEDGER)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MOS_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in MOS_FIELDS})
    from collections import Counter
    print(f"{len(rows)}건 → {a.out}")
    for k, v in sorted(Counter(r.get("상태", "") for r in rows).items()):
        print(f"  {k}: {v}")


def main():
    p = argparse.ArgumentParser(description="요구 안전마진 입력(U_e·L) 계산.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calc", help="한 종목의 U_e·L (내재가치를 주면 요구 안전마진·분할 가격까지)")
    c.add_argument("ticker")
    c.add_argument("--as-of", default="", help="기준일(YYYY-MM-DD). 한국은 그 시점 최신 사업보고서 연도까지")
    c.add_argument("--iv-low", type=float)
    c.add_argument("--iv-high", type=float)
    c.add_argument("--price", type=float, help="보고서 기준가 → 안전마진 줄 출력")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--financial", dest="financial", action="store_true", default=None, help="금융업으로 계산")
    g.add_argument("--nonfinancial", dest="financial", action="store_false", help="비금융으로 계산")
    c.add_argument("--u-e", type=float, default=None, help="원본 없는 시장: 다른 출처로 계산한 U_e(%%)")
    c.add_argument("--l", dest="l_pen", type=float, default=None, help="--u-e 와 함께: 직접 판정한 L(0/5/10)")
    c.add_argument("--note", default="", help="--u-e·--l 의 출처·계산 근거")
    c.add_argument("--json", action="store_true")
    lg = sub.add_parser("ledger", help="판단 원장 전부 계산 → reports/decision-mos.csv")
    lg.add_argument("--ledger", default="")
    lg.add_argument("--out", default=MOS_CSV)
    a = p.parse_args()
    (cmd_calc if a.cmd == "calc" else cmd_ledger)(a)


if __name__ == "__main__":
    run(main)
