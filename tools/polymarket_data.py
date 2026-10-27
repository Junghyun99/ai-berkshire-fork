#!/usr/bin/env python3
"""Polymarket 예측시장 도구 — 공개 Gamma API(키·인증 불필요), 외부 종속성 없음(stdlib만).

금리 인하, 경기침체, 선거, 지정학 같은 미래 사건에 대해 시장이 가격에 반영한 확률을 보여준다.
뉴스(이미 일어난 일)·FRED(현재 상태)와 달리 '군중이 앞으로 일어날 것으로 값을 매긴 것'이다.
확률은 예측이 아니라 거래 가격이며, 거래량이 클수록 신뢰도가 높다.

시점 통제:
  Polymarket은 열려 있는 시장의 실시간 확률만 제공하고 과거 빈티지가 없다.
  그래서 --as-of 가 과거 날짜면 데이터를 보류한다(코드 5). 미래 정보 유출 방지.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)
  tradingagents/dataflows/vendors/polymarket.py 를 stdlib로 이식.

사용법:
    python3 tools/polymarket_data.py search "Fed rate cut"
    python3 tools/polymarket_data.py search "recession 2026" --limit 10

종료 코드: 0 정상 / 3 해당 시장 없음 / 4 출처 장애 / 5 시점 보류 (tools/_us_common.py 참고)
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import json
import math
from datetime import datetime, timezone

from _us_common import NoDataError, get_json, is_historical, parse_as_of, run, withheld

_BASE = "https://gamma-api.polymarket.com"
_DEFAULT_LIMIT = 6


def _json_list(value) -> list:
    """Gamma는 outcomes/outcomePrices를 'JSON 문자열로 된 배열'로 준다."""
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return []


def is_forward_looking(market: dict, now: datetime) -> bool:
    """열려 있고 미래에 결론이 나는 시장만. closed가 신뢰할 수 있는 종료 플래그다(active는 정산 후에도 True)."""
    if market.get("closed"):
        return False
    end = market.get("endDate")
    if end:
        try:
            if datetime.fromisoformat(end.replace("Z", "+00:00")) < now:
                return False
        except ValueError:
            pass
    return bool(_json_list(market.get("outcomePrices"))) and bool(_json_list(market.get("outcomes")))


def fmt_odds(prob: float) -> str:
    """확률을 %로. 0%·100% 근처는 유효숫자 2자리를 남겨 0.05%가 0%로, 99.95%가 100%로 찍히지 않게 한다."""
    def decimals(distance: float) -> int:
        return 1 - math.floor(math.log10(distance))

    if 0 < prob < 0.01:
        pct = prob * 100
        return f"{pct:.{decimals(pct)}f}".rstrip("0").rstrip(".") + "%"
    if 0.99 < prob < 1:
        dist = (1 - prob) * 100
        return f"{100 - dist:.{decimals(dist)}f}".rstrip("0").rstrip(".") + "%"
    return f"{prob:.0%}"


def cmd_search(topic: str, limit: int, as_of: str):
    if is_historical(as_of):
        withheld("Polymarket", "예측시장 확률", as_of,
                 "Polymarket은 열린 시장의 실시간 확률만 제공하고 과거 시점 값이 없습니다.")

    data = get_json(f"{_BASE}/public-search", {"q": topic, "limit_per_type": 20})
    now = datetime.now(timezone.utc)
    markets = [m for ev in data.get("events", []) for m in ev.get("markets", [])
               if is_forward_looking(m, now)]
    markets.sort(key=lambda m: m.get("volumeNum") or 0, reverse=True)
    if not markets:
        raise NoDataError(f"'{topic}' 에 해당하는 열린 예측시장이 없습니다. "
                          f"Polymarket은 거시·정치·지정학·코인 위주라 개별 기업은 없는 경우가 많습니다.")

    print("=" * 72)
    print(f'Polymarket 예측시장: "{topic}" (실시간, 거래량 순)')
    print("  확률은 군중이 매긴 가격이지 확정된 예측이 아니다. 거래량이 클수록 깊고 신뢰도 높음.")
    print("=" * 72)
    for m in markets[:limit]:
        prices, outcomes = _json_list(m.get("outcomePrices")), _json_list(m.get("outcomes"))
        try:
            prob = float(prices[0])
        except (ValueError, IndexError):
            continue
        week = m.get("oneWeekPriceChange")
        week_str = f", 1주 {week * 100:+.1f}%p" if isinstance(week, (int, float)) and week else ""
        print(f"  - {m.get('question')} — {outcomes[0] if outcomes else 'Yes'} {fmt_odds(prob)} "
              f"(거래량 ${m.get('volumeNum') or 0:,.0f}, 결론 {(m.get('endDate') or '')[:10]}{week_str})")
    print("\n  출처: Polymarket Gamma API(gamma-api.polymarket.com).")


def main():
    p = argparse.ArgumentParser(description="Polymarket 예측시장 확률 도구.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("search", help="주제로 열린 예측시장 검색")
    ps.add_argument("topic", help='예: "Fed rate cut", "recession 2026"')
    ps.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    ps.add_argument("--as-of", default="", help="분석 기준일. 과거면 보류(실시간 데이터만 존재)")
    args = p.parse_args()
    cmd_search(args.topic, args.limit, parse_as_of(args.as_of))


if __name__ == "__main__":
    run(main)
