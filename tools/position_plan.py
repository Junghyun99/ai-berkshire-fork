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
  - 축소 검토 가격 = 내재가치 상단 × (1 + 20%)(--trim-premium). 가격과 별개로 반증 조건이 발생하면 축소 검토.
  - 현재 상태: 현재가가 1차 가격대 이하이고 판단이 매수면 '1차 실행 가능', 아니면 '대기'. 관망은 실행하지 않는다.

사용법:
    python3 tools/position_plan.py --from-report reports/삼성전자/최종보고서.md --ticker 005930
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

from _us_common import NoDataError, UnavailableError, run
import decision_ledger as dl

CONVICTION_FACTOR = {1: 0.0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}
_PLAN_RE = re.compile(r"\*\*\s*실행 계획\s*\*\*\s*[:：]")


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


def build_plan(verdict: str, conviction: int, iv_low: float, iv_high: float, price=None, currency="KRW",
               max_weight=10.0, mos=(15, 25, 35), split=(30, 30, 40), trim_premium=20.0, current_weight=None) -> dict:
    if verdict not in dl.VERDICTS:
        raise SystemExit(f"❌ 판단은 매수/관망/회피 중 하나: {verdict}")
    if conviction not in CONVICTION_FACTOR:
        raise SystemExit(f"❌ 확신도는 1~5: {conviction}")
    if len(mos) != len(split):
        raise SystemExit("❌ --mos 와 --split 의 개수가 같아야 합니다.")
    if abs(sum(split) - 100) > 1e-6:
        raise SystemExit(f"❌ --split 합계가 100이 아닙니다: {sum(split)}")
    if not iv_low or not iv_high or iv_low <= 0 or iv_high < iv_low:
        raise NoDataError("내재가치 범위가 없거나 잘못됐습니다(하단 ≤ 상단, 양수). 내재가치 없이 가격대를 만들지 않습니다.")
    mid = (iv_low + iv_high) / 2
    cap = 0.0 if verdict == "회피" else max_weight * CONVICTION_FACTOR[conviction]
    tranches = [{"안전마진": m, "가격": round_price(mid * (1 - m / 100)), "비중": round(cap * s / 100, 2)}
                for m, s in zip(mos, split)]
    trim = round_price(iv_high * (1 + trim_premium / 100))
    plan = {"판단": verdict, "확신도": conviction, "통화": currency, "내재가치하단": iv_low, "내재가치상단": iv_high,
            "내재가치중앙": mid, "비중상한": round(cap, 2), "분할매수": tranches if cap else [], "축소검토가": trim,
            "현재가": price, "현재안전마진": None, "현재상태": "", "보유조정": ""}
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
    if price and price >= trim:
        plan["현재상태"] += " · 현재가가 축소 검토가 이상"
    if current_weight is not None:
        if current_weight > cap:
            plan["보유조정"] = f"현재 비중 {current_weight:g}%가 상한 {cap:g}%를 넘는다 — 초과분 {current_weight - cap:g}%p 정상화 검토"
        else:
            plan["보유조정"] = f"현재 비중 {current_weight:g}% ≤ 상한 {cap:g}% — 추가 여력 {cap - current_weight:g}%p"
    return plan


def plan_line(plan: dict) -> str:
    """보고서에 넣는 고정 형식 줄(--parse 와 report_check 가 읽는다)."""
    c = plan["통화"]
    buys = " / ".join(f"{fmt_price(t['가격'], c)} {t['비중']:g}%" for t in plan["분할매수"]) or "-"
    return (f"**실행 계획**: 비중 상한 {plan['비중상한']:g}% | **분할 매수**: {buys} | "
            f"**축소 검토**: {fmt_price(plan['축소검토가'], c)} 이상 또는 반증 조건 발생 | **현재 상태**: {plan['현재상태']}")


def render(plan: dict) -> str:
    c = plan["통화"]
    lines = ["## 실행 계획 기준선 (tools/position_plan.py — 규칙 기반, 관점)", "",
             f"- 판단 {plan['판단']} · 확신도 ★{plan['확신도']} · 내재가치 {fmt_price(plan['내재가치하단'], c)}~"
             f"{fmt_price(plan['내재가치상단'], c)} (중앙 {fmt_price(round_price(plan['내재가치중앙']), c)})",
             f"- 현재가 {fmt_price(plan['현재가'], c) if plan['현재가'] else '미확인'}"
             + (f" · 중앙값 대비 안전마진 {plan['현재안전마진']:+.1f}%" if plan["현재안전마진"] is not None else ""),
             f"- 비중 상한 {plan['비중상한']:g}% (최대 비중 × 확신도 계수)", ""]
    if plan["분할매수"]:
        lines += ["| 차수 | 안전마진 | 가격 | 비중 |", "|---|---|---|---|"]
        for i, t in enumerate(plan["분할매수"], 1):
            lines.append(f"| {i}차 | {t['안전마진']:g}% | {fmt_price(t['가격'], c)} | {t['비중']:g}% |")
        lines.append("")
    lines += [f"- 축소 검토: {fmt_price(plan['축소검토가'], c)} 이상(내재가치 상단 프리미엄), 또는 반증 조건 발생",
              f"- 현재 상태: {plan['현재상태']}"]
    if plan["보유조정"]:
        lines.append(f"- 보유 조정: {plan['보유조정']}")
    lines += ["", plan_line(plan), "",
              "> 기준선은 출발점이다. 리스크 토론은 이 숫자를 올리거나 내리는 이유를 데이터로 다투고, "
              "바꾼 숫자와 이유를 06-리스크토론-비중.md 에 남긴다."]
    return "\n".join(lines) + "\n"


def parse_plan(text: str) -> dict:
    """보고서의 `**실행 계획**:` 줄 → {비중상한, 분할매수[(가격, 비중)], 축소검토, 현재상태}. 코드 블록 안은 무시."""
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
        m = re.search(r"([\d,]+(?:\.\d+)?)\s*[^\d%/]*?\s+(\d+(?:\.\d+)?)\s*%", part.strip())
        if m:
            tranches.append((float(m.group(1).replace(",", "")), float(m.group(2))))
        elif part.strip() not in ("", "-"):
            raise NoDataError(f"분할 매수 항목을 읽을 수 없습니다: '{part.strip()}' (형식: 가격 비중%)")
    if float(cap.group(1)) > 0 and not tranches:
        raise NoDataError("비중 상한이 0보다 큰데 분할 매수 가격대가 없습니다.")
    total = sum(w for _, w in tranches)
    if total > float(cap.group(1)) + 0.01:
        raise NoDataError(f"분할 매수 비중 합계 {total:g}% 가 비중 상한 {cap.group(1)}% 를 넘습니다.")
    return {"비중상한": float(cap.group(1)), "분할매수": tranches,
            "축소검토": row.get("축소 검토", ""), "현재상태": row.get("현재 상태", "")}


def main():
    p = argparse.ArgumentParser(description="실행 계획 기준선(비중 상한·분할 매수·축소 검토).")
    p.add_argument("--from-report", default="", help="결론 라벨 줄에서 판단·확신도·내재가치를 읽음")
    p.add_argument("--name", default="", help="다중 회사 보고서의 **종목** 값")
    p.add_argument("--ticker", default="", help="현재가 조회(global_stock_data 규칙)")
    p.add_argument("--price", type=float, default=None, help="현재가 직접 지정(조회보다 우선)")
    p.add_argument("--currency", default="", help="통화(기본: 조회 결과, 없으면 KRW)")
    p.add_argument("--verdict", default="")
    p.add_argument("--conviction", type=int, default=None)
    p.add_argument("--iv-low", type=float, default=None)
    p.add_argument("--iv-high", type=float, default=None)
    p.add_argument("--max-weight", type=float, default=10.0, help="확신도 ★5일 때 비중 상한(%%, 기본 10)")
    p.add_argument("--mos", default="15,25,35", help="분할 매수 안전마진(%%, 쉼표)")
    p.add_argument("--split", default="30,30,40", help="차수별 배분(%%, 합 100)")
    p.add_argument("--trim-premium", type=float, default=20.0, help="축소 검토: 내재가치 상단 대비 프리미엄(%%)")
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

    price, currency = a.price, a.currency
    if price is None and a.ticker:
        try:
            _, cur, price = dl.resolve_symbol(a.ticker)
        except NoDataError:
            raise
        except Exception as e:  # noqa: BLE001 — 네트워크 계열 실패는 출처 장애
            raise UnavailableError(f"현재가 조회 실패: {e}")
        currency = currency or cur
    plan = build_plan(verdict, int(conviction), float(low or 0), float(high or 0), price, currency or "KRW",
                      a.max_weight, _pcts(a.mos, "--mos"), _pcts(a.split, "--split"), a.trim_premium,
                      a.current_weight)
    if a.json:
        print(json.dumps(dict(plan, 실행계획줄=plan_line(plan)), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render(plan))


if __name__ == "__main__":
    run(main)
