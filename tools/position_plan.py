#!/usr/bin/env python3
"""실행 계획 기준선 — 판단(매수/관망/회피)·확신도·내재가치에서 비중 상한과 분할 매수 가격대를 규칙으로 계산한다. stdlib만.

리스크 토론(investment-team 7.5단계)의 출발점이다. 세 성향(공격·보수·중립)이 숫자를 지어내지 않고 이 기준선을
'얼마나 올리고 내릴지'만 다투게 한다. 규칙 자체는 관점(가치투자 관행)이며, 바꾸려면 인자로 바꾸고 이유를 쓴다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)의 Trader 거래안
  → Aggressive/Conservative/Neutral 리스크 토론 → Portfolio Manager 최종 결정 흐름.
  원본은 단기 매매 등급(Buy~Sell)을 내지만, 여기서는 가치투자 실행 계획(비중 상한·분할 매수·축소 조건)을 낸다.

기본 규칙(관점, 인자로 변경 가능):
  - 비중 상한 = 최대 비중(--max-weight, 기본 10%) × 확신도 계수(★1 0 / ★2 0.25 / ★3 0.5 / ★4 0.75 / ★5 1.0).
    판단이 회피면 0.
  - 분할 매수 가격대 = 내재가치 중앙값 × (1 − 안전마진). 안전마진 15/25/35%(--mos), 배분 30/30/40%(--split).
  - 신규 매수 금지선 = 내재가치 상단 × (1 + 15%)(--stop-premium). 이 가격 이상에서는 새로 사지 않는다.
  - 축소(보유 시에만): 신규 매수 금지선 이상에서 1/3, 내재가치 상단 × (1 + 30%)(--trim-premium) 이상에서 추가 축소.
    반증 조건이 발생하면 가격과 무관하게 즉시 검토.
  - 현재 상태: 현재가가 1차 가격대 이하이고 판단이 매수면 '1차 실행 가능', 아니면 '대기'. 관망은 실행하지 않는다.

가격대의 현실성(--ticker 를 주면 자동): 차수마다 현재가 대비 하락률과 52주 최저·3년 최저 대비 위치를 붙인다.
  가격은 바꾸지 않고 표시만 한다(가격을 고치는 것은 리스크 토론의 몫). 모든 차수가 52주 최저 아래면 경고한다.
  2026-10-28 MSFT 실행에서 기준선의 축소 검토가가 현재가 +0.28%, 2·3차 가격이 52주 최저 아래로 나와
  세 성향이 모두 고친 것을 반영한 개선이다.

사용법:
    python3 tools/position_plan.py --from-report reports/삼성전자/최종보고서.md --ticker 005930
    python3 tools/position_plan.py --from-report {보고서} --ticker MSFT --price 531.33   # 보고서 기준가로 계산, 범위는 조회
    python3 tools/position_plan.py --verdict 매수 --conviction 4 --iv-low 180000 --iv-high 220000 --price 150000
    python3 tools/position_plan.py ... --current-weight 7 --json      # 보유 중이면 현재 비중, 기계용 JSON
    python3 tools/position_plan.py --parse reports/삼성전자/최종보고서.md # 보고서의 **실행 계획** 줄 판독(자동매매 연동용)

종료 코드: 0 정상 / 3 입력 판독 불가(라벨 줄·실행 계획 줄 없음) / 4 시세 조회 장애
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone

from _us_common import NoDataError, UnavailableError, run
import decision_ledger as dl

CONVICTION_FACTOR = {1: 0.0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}
_PLAN_RE = re.compile(r"\*\*\s*실행 계획\s*\*\*\s*[:：]")
_TRANCHE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*[^\d%/(]*?\s+(\d+(?:\.\d+)?)\s*%")


def _pcts(value: str, name: str) -> list:
    try:
        out = [float(x) for x in value.split(",") if x.strip()]
    except ValueError:
        raise SystemExit(f"❌ {name} 는 쉼표로 구분한 숫자(%)여야 합니다: {value}")
    if not out:
        raise SystemExit(f"❌ {name} 가 비었습니다.")
    return out


def round_price(x: float) -> float:
    """원화 등 큰 단위는 100단위, 작은 단위(달러 등)는 소수 둘째 자리."""
    return float(round(x / 100) * 100) if x >= 1000 else round(x, 2)


def fmt_price(x: float, currency: str) -> str:
    unit = {"KRW": "원", "USD": " USD", "HKD": " HKD", "CNY": " CNY", "JPY": "엔"}.get(currency, f" {currency}".rstrip())
    return f"{x:,.0f}{unit}" if x >= 1000 else f"{x:,.2f}{unit}"


def fetch_ranges(symbol: str) -> dict:
    """Yahoo 일봉 3년 → {52주최저, 3년최저, 3년최저일}. 원주가(수정 전) 저가 기준이라 현재가와 같은 단위다."""
    from global_stock_data import _get_json
    data = _get_json(f"/v8/finance/chart/{symbol}", {"range": "3y", "interval": "1d"})
    res = ((data.get("chart") or {}).get("result") or [None])[0] or {}
    meta, stamps = res.get("meta") or {}, res.get("timestamp") or []
    lows = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("low") or []
    pts = [(t, v) for t, v in zip(stamps, lows) if isinstance(v, (int, float)) and v > 0]
    if not pts:
        raise NoDataError(f"{symbol} 의 3년 가격 기록이 없습니다.")
    t3, low3 = min(pts, key=lambda p: p[1])
    year_ago = pts[-1][0] - 365 * 86400
    low52 = meta.get("fiftyTwoWeekLow") or min(v for t, v in pts if t >= year_ago)
    off = meta.get("gmtoffset", 0)
    return {"52주최저": float(low52), "3년최저": float(low3),
            "3년최저일": datetime.fromtimestamp(t3 + off, tz=timezone.utc).strftime("%Y-%m-%d")}


def build_plan(verdict: str, conviction: int, iv_low: float, iv_high: float, price=None, currency="KRW",
               max_weight=10.0, mos=(15, 25, 35), split=(30, 30, 40), stop_premium=15.0, trim_premium=30.0,
               current_weight=None, ranges=None) -> dict:
    if verdict not in dl.VERDICTS:
        raise SystemExit(f"❌ 판단은 매수/관망/회피 중 하나: {verdict}")
    if conviction not in CONVICTION_FACTOR:
        raise SystemExit(f"❌ 확신도는 1~5: {conviction}")
    if len(mos) != len(split):
        raise SystemExit("❌ --mos 와 --split 의 개수가 같아야 합니다.")
    if abs(sum(split) - 100) > 1e-6:
        raise SystemExit(f"❌ --split 합계가 100이 아닙니다: {sum(split)}")
    if trim_premium <= stop_premium:
        raise SystemExit("❌ --trim-premium 은 --stop-premium 보다 커야 합니다(추가 축소선이 금지선 위).")
    if not iv_low or not iv_high or iv_low <= 0 or iv_high < iv_low:
        raise NoDataError("내재가치 범위가 없거나 잘못됐습니다(하단 ≤ 상단, 양수). 내재가치 없이 가격대를 만들지 않습니다.")
    mid = (iv_low + iv_high) / 2
    cap = 0.0 if verdict == "회피" else max_weight * CONVICTION_FACTOR[conviction]
    tranches = [{"안전마진": m, "가격": round_price(mid * (1 - m / 100)), "비중": round(cap * s / 100, 2)}
                for m, s in zip(mos, split)] if cap else []
    stop = round_price(iv_high * (1 + stop_premium / 100))
    trim = round_price(iv_high * (1 + trim_premium / 100))
    plan = {"판단": verdict, "확신도": conviction, "통화": currency, "내재가치하단": iv_low, "내재가치상단": iv_high,
            "내재가치중앙": mid, "비중상한": round(cap, 2), "분할매수": tranches,
            "신규매수금지가": stop, "축소": [{"가격": stop, "규모": "1/3"}, {"가격": trim, "규모": "추가"}],
            "현재가": price, "현재안전마진": None, "현재상태": "", "보유조정": "", "가격범위": ranges, "경고": []}
    warn = plan["경고"]
    if price:
        plan["현재안전마진"] = round((1 - price / mid) * 100, 1)
    if verdict == "회피" or not cap:
        plan["현재상태"] = "신규 매수 없음(회피)" if verdict == "회피" else "신규 매수 없음(확신도 ★1)"
    elif price is None:
        plan["현재상태"] = "현재가 미확인"
    else:
        hit = [t for t in tranches if price <= t["가격"]]
        if verdict == "매수" and hit:
            plan["현재상태"] = f"{len(hit)}차까지 실행 가능(현재가 ≤ {fmt_price(hit[-1]['가격'], currency)})"
        elif verdict == "매수":
            plan["현재상태"] = "대기(현재가가 1차 가격대 위)"
        else:
            plan["현재상태"] = "대기(관망 — 가격대 도달 시 판단 재검토 후 실행)"
    if price and price >= stop:
        plan["현재상태"] += " · 현재가가 신규 매수 금지 구간"
        warn.append(f"현재가 {fmt_price(price, currency)}가 신규 매수 금지선 {fmt_price(stop, currency)} 이상이다.")
    if not current_weight:
        warn.append("보유 비중이 없거나 미제공이라 축소 규칙은 지금 실행할 것이 없다(보유 시에만 적용). "
                    "지금 작동하는 규칙은 신규 매수 금지선이다.")
    else:
        if current_weight > cap:
            plan["보유조정"] = f"현재 비중 {current_weight:g}%가 상한 {cap:g}%를 넘는다 — 초과분 {current_weight - cap:g}%p 정상화 검토"
        else:
            plan["보유조정"] = f"현재 비중 {current_weight:g}% ≤ 상한 {cap:g}% — 추가 여력 {cap - current_weight:g}%p"
    _annotate_reach(plan)
    return plan


def _annotate_reach(plan: dict) -> None:
    """차수마다 현재가 대비 하락률과 52주·3년 최저 대비 위치를 붙인다. 가격은 바꾸지 않는다."""
    price, rng = plan["현재가"], plan["가격범위"]
    for t in plan["분할매수"]:
        t["현재가대비"] = round((t["가격"] / price - 1) * 100, 1) if price else None
        t["위치"] = ""
        if rng:
            if t["가격"] < rng["3년최저"]:
                t["위치"] = "3년 최저 아래(관측 범위 밖)"
            elif t["가격"] < rng["52주최저"]:
                t["위치"] = "52주 최저 아래"
            else:
                t["위치"] = "52주 범위 안"
    if rng and plan["분할매수"] and all(t["가격"] < rng["52주최저"] for t in plan["분할매수"]):
        plan["경고"].append(f"모든 차수가 52주 최저 {fmt_price(rng['52주최저'], plan['통화'])} 아래다 — 체결 가능성이 낮다. "
                           "리스크 토론에서 가격대의 현실성을 따질 것.")
    elif rng is None and plan["분할매수"]:
        plan["경고"].append("가격 범위를 확인하지 못했다(--ticker 필요) — 차수 가격의 도달 가능성은 따로 확인할 것.")


def plan_line(plan: dict) -> str:
    """보고서에 넣는 고정 형식 줄(--parse 와 report_check 가 읽는다)."""
    c = plan["통화"]
    buys = " / ".join(f"{fmt_price(t['가격'], c)} {t['비중']:g}%" for t in plan["분할매수"]) or "-"
    stop, trim = plan["축소"][0]["가격"], plan["축소"][1]["가격"]
    return (f"**실행 계획**: 비중 상한 {plan['비중상한']:g}% | **분할 매수**: {buys} | "
            f"**축소 검토**: {fmt_price(stop, c)} 이상 신규 매수 금지, 보유 시 {fmt_price(stop, c)} 이상 1/3·"
            f"{fmt_price(trim, c)} 이상 추가 축소, 반증 조건 발생 시 가격과 무관하게 즉시 | "
            f"**현재 상태**: {plan['현재상태']}")


def render(plan: dict) -> str:
    c, rng = plan["통화"], plan["가격범위"]
    lines = ["## 실행 계획 기준선 (tools/position_plan.py — 규칙 기반, 관점)", "",
             f"- 판단 {plan['판단']} · 확신도 ★{plan['확신도']} · 내재가치 {fmt_price(plan['내재가치하단'], c)}~"
             f"{fmt_price(plan['내재가치상단'], c)} (중앙 {fmt_price(round_price(plan['내재가치중앙']), c)})",
             f"- 현재가 {fmt_price(plan['현재가'], c) if plan['현재가'] else '미확인'}"
             + (f" · 중앙값 대비 안전마진 {plan['현재안전마진']:+.1f}%" if plan["현재안전마진"] is not None else ""),
             f"- 비중 상한 {plan['비중상한']:g}% (최대 비중 × 확신도 계수)"]
    if rng:
        lines.append(f"- 가격 범위: 52주 최저 {fmt_price(rng['52주최저'], c)} · 3년 최저 {fmt_price(rng['3년최저'], c)}"
                     f"({rng['3년최저일']}) — Yahoo 일봉 저가")
    lines.append("")
    if plan["분할매수"]:
        lines += ["| 차수 | 안전마진 | 가격 | 비중 | 현재가 대비 | 가격 범위 대비 |", "|---|---|---|---|---|---|"]
        for i, t in enumerate(plan["분할매수"], 1):
            gap = f"{t['현재가대비']:+.1f}%" if t["현재가대비"] is not None else "-"
            lines.append(f"| {i}차 | {t['안전마진']:g}% | {fmt_price(t['가격'], c)} | {t['비중']:g}% | {gap} | "
                         f"{t['위치'] or '미확인'} |")
        lines.append("")
    stop, trim = plan["축소"][0]["가격"], plan["축소"][1]["가격"]
    lines += [f"- 신규 매수 금지: {fmt_price(stop, c)} 이상(내재가치 상단 프리미엄)",
              f"- 축소(보유 시): {fmt_price(stop, c)} 이상 1/3 · {fmt_price(trim, c)} 이상 추가 · 반증 조건 발생 시 가격과 무관하게 즉시",
              f"- 현재 상태: {plan['현재상태']}"]
    if plan["보유조정"]:
        lines.append(f"- 보유 조정: {plan['보유조정']}")
    if plan["경고"]:
        lines += [""] + [f"> ⚠️ {w}" for w in plan["경고"]]
    lines += ["", plan_line(plan), "",
              "> 기준선은 출발점이다. 리스크 토론은 이 숫자를 올리거나 내리는 이유를 데이터로 다투고, "
              "바꾼 숫자와 이유를 06-리스크토론-비중.md 에 남긴다."]
    return "\n".join(lines) + "\n"


def parse_plan(text: str) -> dict:
    """보고서의 `**실행 계획**:` 줄 → {비중상한, 분할매수[{가격, 비중, 조건}], 축소검토, 현재상태}. 코드 블록 안은 무시.

    차수 뒤 괄호의 조건(예: '377 USD 1.5%(1.0%, 확인 신호 시 +0.5%)')은 '조건'으로 남긴다 — 자동매매 쪽에서
    조건이 붙은 주문을 따로 보류할 수 있게.
    """
    rows, fenced = [], False
    for line in unicodedata.normalize("NFKC", text).splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and _PLAN_RE.search(line):
            rows.append({k.strip(): v.strip() for k, v in dl._FIELD_RE.findall(line)})
    if not rows:
        raise NoDataError("**실행 계획** 줄을 찾지 못했습니다.")
    if len({json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows}) > 1:
        raise NoDataError("**실행 계획** 줄이 서로 다르게 여러 번 나옵니다 — 어느 것이 최종인지 알 수 없습니다.")
    row = rows[0]
    cap = re.search(r"(\d+(?:\.\d+)?)\s*%", row.get("실행 계획", ""))
    if not cap:
        raise NoDataError(f"비중 상한을 읽을 수 없습니다: '{row.get('실행 계획', '')}'")
    tranches = []
    for part in (row.get("분할 매수", "") or "").split("/"):
        part = part.strip()
        m = _TRANCHE_RE.search(part)
        if m:
            rest = part[m.end():].strip()
            cond = rest[1:-1].strip() if rest.startswith("(") and rest.endswith(")") else rest
            tranches.append({"가격": float(m.group(1).replace(",", "")), "비중": float(m.group(2)), "조건": cond})
        elif part not in ("", "-"):
            raise NoDataError(f"분할 매수 항목을 읽을 수 없습니다: '{part}' (형식: 가격 비중% (조건))")
    if float(cap.group(1)) > 0 and not tranches:
        raise NoDataError("비중 상한이 0보다 큰데 분할 매수 가격대가 없습니다.")
    total = sum(t["비중"] for t in tranches)
    if total > float(cap.group(1)) + 0.01:
        raise NoDataError(f"분할 매수 비중 합계 {total:g}% 가 비중 상한 {cap.group(1)}% 를 넘습니다.")
    return {"비중상한": float(cap.group(1)), "분할매수": tranches,
            "축소검토": row.get("축소 검토", ""), "현재상태": row.get("현재 상태", "")}


def main():
    p = argparse.ArgumentParser(description="실행 계획 기준선(비중 상한·분할 매수·신규 매수 금지·축소).")
    p.add_argument("--from-report", default="", help="결론 라벨 줄에서 판단·확신도·내재가치를 읽음")
    p.add_argument("--name", default="", help="다중 회사 보고서의 **종목** 값")
    p.add_argument("--ticker", default="", help="현재가·가격 범위 조회(global_stock_data 규칙)")
    p.add_argument("--price", type=float, default=None, help="현재가 직접 지정(조회보다 우선, 예: 보고서 기준가)")
    p.add_argument("--currency", default="", help="통화(기본: 조회 결과, 없으면 KRW)")
    p.add_argument("--verdict", default="")
    p.add_argument("--conviction", type=int, default=None)
    p.add_argument("--iv-low", type=float, default=None)
    p.add_argument("--iv-high", type=float, default=None)
    p.add_argument("--max-weight", type=float, default=10.0, help="확신도 ★5일 때 비중 상한(%%, 기본 10)")
    p.add_argument("--mos", default="15,25,35", help="분할 매수 안전마진(%%, 쉼표)")
    p.add_argument("--split", default="30,30,40", help="차수별 배분(%%, 합 100)")
    p.add_argument("--stop-premium", type=float, default=15.0, help="신규 매수 금지·1차 축소: 내재가치 상단 대비(%%)")
    p.add_argument("--trim-premium", type=float, default=30.0, help="추가 축소: 내재가치 상단 대비(%%)")
    p.add_argument("--current-weight", type=float, default=None, help="현재 보유 비중(%%)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--parse", default="", help="보고서의 **실행 계획** 줄을 판독해 JSON으로 출력")
    a = p.parse_args()

    if a.parse:
        with open(a.parse, encoding="utf-8") as f:
            print(json.dumps(parse_plan(f.read()), ensure_ascii=False, indent=2))
        return

    verdict, conviction, low, high = a.verdict, a.conviction, a.iv_low, a.iv_high
    if a.from_report:
        with open(a.from_report, encoding="utf-8") as f:
            label = dl.parse_label(f.read(), a.name)
        verdict = dl._merge(verdict, label["판단"], "판단")
        conviction = dl._merge(conviction, label["확신도"], "확신도")
        low = dl._merge(low, float(label["내재가치하단"]) if label["내재가치하단"] else None, "내재가치 하단")
        high = dl._merge(high, float(label["내재가치상단"]) if label["내재가치상단"] else None, "내재가치 상단")
    if not verdict or conviction is None:
        raise SystemExit("❌ --from-report 또는 --verdict·--conviction 이 필요합니다.")

    price, currency, ranges = a.price, a.currency, None
    if a.ticker:
        try:
            symbol, cur, live = dl.resolve_symbol(a.ticker)
            ranges = fetch_ranges(symbol)
        except NoDataError:
            raise
        except Exception as e:  # noqa: BLE001 — 네트워크 계열 실패는 출처 장애
            raise UnavailableError(f"시세 조회 실패: {e}")
        price = live if price is None else price
        currency = currency or cur
    plan = build_plan(verdict, int(conviction), float(low or 0), float(high or 0), price, currency or "KRW",
                      a.max_weight, _pcts(a.mos, "--mos"), _pcts(a.split, "--split"), a.stop_premium,
                      a.trim_premium, a.current_weight, ranges)
    if a.json:
        print(json.dumps(dict(plan, 실행계획줄=plan_line(plan)), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render(plan))


if __name__ == "__main__":
    run(main)
