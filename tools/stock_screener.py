#!/usr/bin/env python3
"""
stock_screener.py — 모멘텀 발견 + 가치검증 주식선택 화면
용법：
  python3 stock_screener.py                   # 모두 스캔 watchlist
  python3 stock_screener.py NVDA TSLA GOOG    # 지정된 대상을 스캔
  python3 stock_screener.py --update MU       # 고쳐 쓰다 MU 기본 데이터

액자：
  레이어 1(모멘텀 발견）：60일일 최고 + 볼륨 확인 → 대기 풀에 입장
  두 번째 레이어(값 검증）：6차원 점수 ≥ 3/6 → 매수 신호
  신호 분류：3/6=테스트 챔버3% | 4/6=표준창고5% | 5-6/6=입장을 확실히 하세요8%

개선 사항(~NVDA/AMD/MU백테스트）：
  1. 매출총이익률 연속2분기별 개선 → 독립적인 바이인 조건(해결NVDA 2023-01판단을 놓쳤다）
  2. EPS기대를 초과했습니다>30% → 순환적 재고독립조건(solveMU하단 신호）
  3. 신호 등급은 이진 판단을 대체합니다.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from collections import OrderedDict

# ============================================================
# 구성
# ============================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FUND_FILE = os.path.join(DATA_DIR, "fundamentals.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

DEFAULT_WATCHLIST = {
    "us_ai_chip": ["NVDA", "AMD", "MU", "AVGO", "MRVL", "TSM"],
    "us_ai_app": ["GOOG", "META", "MSFT", "AMZN", "CRM", "NOW", "PLTR"],
    "us_ai_infra": ["ETN", "PWR", "VRT", "CRWV"],
    "us_crypto": ["COIN", "HOOD", "MSTR", "CRCL"],
    "hk_internet": ["0700.HK", "9888.HK", "1024.HK", "9992.HK"],
    "a_share": [],  # A주식에는 다양한 데이터 소스가 필요하며 나중에 확장될 예정입니다.
}

# ============================================================
# 가격 데이터 수집(경유curl우회로Python SSL질문）
# ============================================================

def fetch_prices_curl(ticker, days=120):
    """사용curl얻다Yahoo Finance일일 데이터"""
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )
    try:
        result = subprocess.run(
            ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        chart = data.get("chart", {}).get("result", [{}])[0]
        timestamps = chart.get("timestamp", [])
        quote = chart.get("indicators", {}).get("quote", [{}])[0]
        rows = []
        for i, ts in enumerate(timestamps):
            c = quote.get("close", [None] * len(timestamps))[i]
            v = quote.get("volume", [None] * len(timestamps))[i]
            h = quote.get("high", [None] * len(timestamps))[i]
            if c and v and h:
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                rows.append({"date": dt, "close": c, "high": h, "volume": v})
        return rows if len(rows) > 60 else None
    except Exception as e:
        return None


# ============================================================
# 기초 데이터 관리
# ============================================================

def load_fundamentals():
    """기본 데이터 로드"""
    if os.path.exists(FUND_FILE):
        with open(FUND_FILE) as f:
            return json.load(f)
    return {}


def save_fundamentals(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FUND_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_fundamental_interactive(ticker):
    """기본 데이터를 대화형으로 업데이트"""
    funds = load_fundamentals()
    if ticker not in funds:
        funds[ticker] = {"quarters": {}}
    print(f"\n  고쳐 쓰다 {ticker} 기본 데이터")
    print(f"  이미 분기가 있습니다：{', '.join(funds[ticker]['quarters'].keys()) or '없음'}")
    date = input("  재무 보고서 발표일 (YYYY-MM-DD): ").strip()
    label = input("  상표 (좋다 Q1 2024): ").strip()
    rev_yoy = float(input("  전년 대비 매출 성장 (%): "))
    gm = float(input("  매출총이익률 (%): "))
    eps_beat = float(input("  EPS기대를 초과했습니다 (%): "))

    funds[ticker]["quarters"][date] = {
        "label": label, "rev_yoy": rev_yoy, "gm": gm, "eps_beat": eps_beat
    }
    save_fundamentals(funds)
    print(f"  ✅ 저장됨 {ticker} {label}")


# ============================================================
# 레벨 1: 추진력 발견
# ============================================================

def check_momentum(prices):
    """가장 최근 거래일에 모멘텀 신호가 발생했는지 확인하세요."""
    if len(prices) < 61:
        return None

    latest = prices[-1]
    close = latest["close"]

    # 60일일 최고
    past_60_highs = [p["high"] for p in prices[-61:-1]]
    is_60d_high = close > max(past_60_highs)

    # 큰 볼륨: 거의5일일 평균 거래량 > 20일일 평균 거래량 × 1.5
    vol_5 = sum(p["volume"] for p in prices[-5:]) / 5
    vol_20 = sum(p["volume"] for p in prices[-20:]) / 20
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 0
    is_volume = vol_ratio > 1.5

    # 30일일 증가
    close_30d = prices[-31]["close"] if len(prices) > 30 else prices[0]["close"]
    pct_30d = (close - close_30d) / close_30d * 100

    # 닫다5매일매일 돌파하는 날이 있다(꼭 오늘은 아니다)）
    recent_breakout = False
    for i in range(-5, 0):
        if prices[i]["close"] > max(p["high"] for p in prices[i-60:i]):
            recent_breakout = True
            break

    triggered = (is_60d_high or recent_breakout) and is_volume

    return {
        "triggered": triggered,
        "close": round(close, 2),
        "date": latest["date"],
        "is_60d_high": is_60d_high,
        "vol_ratio": round(vol_ratio, 2),
        "pct_30d": round(pct_30d, 1),
    }


# ============================================================
# 두 번째 수준: 가치 검증（6백테스트 개선을 포함한 차원）
# ============================================================

def check_value(ticker, signal_date=None):
    """6치수 값 확인"""
    funds = load_fundamentals()
    if ticker not in funds or not funds[ticker].get("quarters"):
        return None

    quarters = funds[ticker]["quarters"]
    sorted_q = sorted(quarters.items(), key=lambda x: x[0])

    # 지난 2분기 찾기
    if signal_date:
        valid = [(d, q) for d, q in sorted_q if d <= signal_date]
    else:
        valid = sorted_q

    if not valid:
        return None

    latest = valid[-1]
    prev = valid[-2] if len(valid) >= 2 else None
    prev2 = valid[-3] if len(valid) >= 3 else None

    d = latest[1]
    pd = prev[1] if prev else None
    pd2 = prev2[1] if prev2 else None

    checks = {}

    # 1. 매출이 가속화되고 있습니다 (전년 대비 성장이 개선되고 있습니다)）
    if pd:
        checks["수익 가속화"] = d["rev_yoy"] > pd["rev_yoy"]
    else:
        checks["수익 가속화"] = d["rev_yoy"] > 20

    # 2. 매출총이익률 방향
    if pd:
        checks["매출총이익률 확대"] = d["gm"] > pd["gm"] or d["gm"] > 55
    else:
        checks["매출총이익률 확대"] = d["gm"] > 45

    # 3. EPS기대를 초과했습니다 > 10%
    checks["놀라운 이익"] = d["eps_beat"] > 10

    # 4. 높은 수익 성장 > 15%
    checks["높은 수익 성장"] = d["rev_yoy"] > 15

    # 5. 건전한 매출총이익률 > 40%
    checks["건전한 매출총이익률"] = d["gm"] > 40

    # 6. ★개선: 매출총이익률 지속2분기별 개선(해결NVDA 2023-01판단을 놓쳤다）
    if pd and pd2:
        checks["총이익은 지속적으로 개선되고 있습니다."] = d["gm"] > pd["gm"] > pd2["gm"]
    elif pd:
        checks["총이익은 지속적으로 개선되고 있습니다."] = d["gm"] > pd["gm"]
    else:
        checks["총이익은 지속적으로 개선되고 있습니다."] = False

    score = sum(1 for v in checks.values() if v)

    # ★개선: 독립 합격 조건
    independent_pass = False
    independent_reason = ""

    # 상태A：매출총이익률 연속2분기별 개선 + 총 이익>45%（NVDA 2023-01장면）
    if checks.get("총이익은 지속적으로 개선되고 있습니다.") and d["gm"] > 45:
        independent_pass = True
        independent_reason = "매출총이익률은 지속적으로 개선되고 있습니다.+>45%"

    # 상태B：EPS기대를 초과했습니다>30%（MU하단 장면）
    if d["eps_beat"] > 30:
        independent_pass = True
        independent_reason = "EPS기대를 초과했습니다>30%（순환적인 주식 신호）"

    return {
        "score": score,
        "max": 6,
        "checks": checks,
        "fund": d,
        "fund_date": latest[0],
        "fund_label": d.get("label", ""),
        "independent_pass": independent_pass,
        "independent_reason": independent_reason,
    }


# ============================================================
# 신호 분류
# ============================================================

def grade_signal(momentum, value):
    """종합평가"""
    if not momentum or not momentum["triggered"]:
        return "SKIP", "모멘텀 신호 없음", ""

    if not value:
        return "WATCH", "모멘텀 트리거이지만 기본 데이터가 없음", "보충 기초"

    score = value["score"]
    ind = value["independent_pass"]

    if score >= 5 or (score >= 4 and ind):
        return "BUY_8%", f"입장을 확실히 하세요（{score}/6）", "제안8%위치"
    elif score >= 4 or (score >= 3 and ind):
        return "BUY_5%", f"표준창고（{score}/6）", "제안5%위치"
    elif score >= 3:
        return "BUY_3%", f"테스트 챔버（{score}/6）", "제안3%위치"
    elif ind:
        return "BUY_3%", f"독립조건 통과：{value['independent_reason']}", "제안3%위치"
    else:
        return "PASS", f"모멘텀은 있으나 펀더멘탈이 부족함（{score}/6）", "계속해서 관찰하세요"


# ============================================================
# 대상 스캔
# ============================================================

def scan_ticker(ticker, verbose=True):
    """단일 대상 스캔"""
    prices = fetch_prices_curl(ticker)
    if not prices:
        if verbose:
            print(f"  {ticker:<8} ⚠️  가격 데이터를 가져올 수 없습니다.")
        return None

    momentum = check_momentum(prices)
    value = check_value(ticker)
    grade, reason, advice = grade_signal(momentum, value)

    result = {
        "ticker": ticker,
        "grade": grade,
        "reason": reason,
        "advice": advice,
        "momentum": momentum,
        "value": value,
    }

    if verbose:
        # 컴팩트한 출력
        m = momentum
        symbol = {"BUY_8%": "🔴", "BUY_5%": "🟡", "BUY_3%": "🟢", "WATCH": "👀", "PASS": "⬜", "SKIP": "  "}
        s = symbol.get(grade, "  ")

        if grade.startswith("BUY"):
            print(f"  {s} {ticker:<8} ${m['close']:<8} 30낮+{m['pct_30d']}% 볼륨을 높이세요{m['vol_ratio']}x  → {grade} {reason}")
            if value:
                v = value
                checks_str = " ".join(f"{'✅' if val else '❌'}{k}" for k, val in v["checks"].items())
                print(f"     기초({v['fund_label']}): 수익{v['fund']['rev_yoy']}% 총 이익{v['fund']['gm']}% EPS추월하다{v['fund']['eps_beat']}%")
                print(f"     {checks_str}")
                if v["independent_pass"]:
                    print(f"     ★독립적으로 통과：{v['independent_reason']}")
        elif grade == "WATCH":
            print(f"  {s} {ticker:<8} ${m['close']:<8} 30낮+{m['pct_30d']}%  → 모멘텀 트리거! 기초자료 보완 필요")
        elif grade == "PASS":
            print(f"  {s} {ticker:<8} ${m['close']:<8}  → {reason}")
        # SKIP출력 없음

    return result


# ============================================================
# 메인 프로그램
# ============================================================

def main():
    args = sys.argv[1:]

    # 업데이트 모드
    if args and args[0] == "--update":
        ticker = args[1] if len(args) > 1 else input("  타겟 코드: ").strip().upper()
        update_fundamental_interactive(ticker)
        return

    # 기본값 초기화watchlist
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(DEFAULT_WATCHLIST, f, indent=2)
        print(f"  기본 생성됨watchlist: {WATCHLIST_FILE}")

    # 스캔 범위 결정
    if args:
        tickers = [t.upper() for t in args]
    else:
        with open(WATCHLIST_FILE) as f:
            wl = json.load(f)
        tickers = []
        for group, syms in wl.items():
            tickers.extend(syms)

    # 스캔 수행
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*70}")
    print(f"  모멘텀 발견 + 가치검증 주식선택 화면  {today}")
    print(f"  스캔 범위：{len(tickers)} 목표")
    print(f"{'='*70}\n")

    buy_signals = []
    watch_signals = []

    for ticker in tickers:
        result = scan_ticker(ticker)
        if result:
            if result["grade"].startswith("BUY"):
                buy_signals.append(result)
            elif result["grade"] == "WATCH":
                watch_signals.append(result)

    # 요약
    print(f"\n{'='*70}")
    print(f"  📋 스캔 결과 요약")
    print(f"{'='*70}")

    if buy_signals:
        print(f"\n  🎯 매수 신호：{len(buy_signals)} 개인")
        for s in sorted(buy_signals, key=lambda x: x["grade"], reverse=True):
            m = s["momentum"]
            print(f"     {s['grade']:<8} {s['ticker']:<8} ${m['close']:<8} {s['reason']}")
    else:
        print(f"\n  매수 신호 없음")

    if watch_signals:
        print(f"\n  👀 관찰(기본 보충 필요）：{len(watch_signals)} 개인")
        for s in watch_signals:
            m = s["momentum"]
            print(f"     {s['ticker']:<8} ${m['close']:<8} 30낮+{m['pct_30d']}% — 이용해주세요 --update {s['ticker']} 다시 채우다")

    print(f"\n  기본 데이터 파일：{FUND_FILE}")
    print(f"  Watchlist문서：{WATCHLIST_FILE}")
    print(f"  사용 --update TICKER 다시 채우다/기본 사항 업데이트\n")


if __name__ == "__main__":
    main()
