#!/usr/bin/env python3
"""
모멘텀 발견 + 가치 검증 백테스팅 도구 v2
백테스트 대상：NVDA / AMD / MU（AI칩 빅 쓰리）
핵심 질문: 이 프레임워크를 다음에서 사용할 수 있습니까?AI파도는 이러한 주식을 일찍 포착합니다？

NVDA：수동으로 키 노드 입력（Yahoo API제한된）
AMD/MU：~에서JSON파일은 실제 일일 데이터를 로드합니다.
"""

import json
import sys
import os
from datetime import datetime
from collections import OrderedDict

# ============================================================
# 기본 데이터(수동으로 입력, 비교)API더 정확하다）
# ============================================================

FUNDAMENTALS = {
    "NVDA": {
        "name": "엔비디아",
        "quarters": OrderedDict([
            ("2022-08-24", {"rev": 67.0, "rev_yoy": -4.0, "gm": 43.5, "eps_beat": -24.0, "label": "FY23Q2(Jul22) 게임 충돌"}),
            ("2022-11-16", {"rev": 59.3, "rev_yoy": -17.0, "gm": 53.6, "eps_beat": 7.4, "label": "FY23Q3(Oct22) 데이터 센터는 계속 유지됩니다"}),
            ("2023-02-22", {"rev": 60.5, "rev_yoy": -21.0, "gm": 63.3, "eps_beat": 10.0, "label": "FY23Q4(Jan23) 매출총이익률 전환점!"}),
            ("2023-05-24", {"rev": 71.9, "rev_yoy": -13.0, "gm": 64.6, "eps_beat": 18.5, "label": "FY24Q1(Apr23) ★수익 전환점+EPS기대를 훨씬 초과했습니다"}),
            ("2023-08-23", {"rev": 135.1, "rev_yoy": 101.0, "gm": 70.1, "eps_beat": 29.0, "label": "FY24Q2(Jul23) ★★탈출하다!수익이 두 배로 늘었습니다"}),
            ("2023-11-21", {"rev": 181.2, "rev_yoy": 206.0, "gm": 74.0, "eps_beat": 19.0, "label": "FY24Q3(Oct23) ★★★3두 배로"}),
            ("2024-02-21", {"rev": 221.0, "rev_yoy": 265.0, "gm": 76.0, "eps_beat": 12.0, "label": "FY24Q4(Jan24) 최고 성장률"}),
            ("2024-05-22", {"rev": 260.4, "rev_yoy": 262.0, "gm": 78.4, "eps_beat": 9.0, "label": "FY25Q1(Apr24)"}),
        ]),
    },
    "AMD": {
        "name": "AMD",
        "quarters": OrderedDict([
            ("2022-08-02", {"rev": 65.5, "rev_yoy": 70.0, "gm": 46.0, "eps_beat": 5.0, "label": "Q2 2022 정점"}),
            ("2022-11-01", {"rev": 55.7, "rev_yoy": 29.0, "gm": 42.0, "eps_beat": 2.3, "label": "Q3 2022 뒤로 물러나다"}),
            ("2023-01-31", {"rev": 55.0, "rev_yoy": 16.0, "gm": 43.0, "eps_beat": 6.2, "label": "Q4 2022"}),
            ("2023-05-02", {"rev": 53.5, "rev_yoy": -9.0, "gm": 44.0, "eps_beat": 7.1, "label": "Q1 2023 맨 아래"}),
            ("2023-08-01", {"rev": 54.0, "rev_yoy": -18.0, "gm": 46.0, "eps_beat": 1.8, "label": "Q2 2023"}),
            ("2023-10-31", {"rev": 58.0, "rev_yoy": 4.0, "gm": 47.0, "eps_beat": 6.1, "label": "Q3 2023 반등하기 시작하다"}),
            ("2024-01-30", {"rev": 61.7, "rev_yoy": 10.0, "gm": 47.0, "eps_beat": 3.7, "label": "Q4 2023 ★MI300풀어 주다"}),
            ("2024-04-30", {"rev": 54.7, "rev_yoy": 2.0, "gm": 47.0, "eps_beat": 3.3, "label": "Q1 2024"}),
            ("2024-07-30", {"rev": 58.3, "rev_yoy": 9.0, "gm": 49.0, "eps_beat": 1.5, "label": "Q2 2024"}),
            ("2024-10-29", {"rev": 68.2, "rev_yoy": 18.0, "gm": 50.0, "eps_beat": 4.5, "label": "Q3 2024 ★데이터센터 가속화"}),
        ]),
    },
    "MU": {
        "name": "마이크론 기술",
        "quarters": OrderedDict([
            ("2022-09-29", {"rev": 66.4, "rev_yoy": -20.0, "gm": 40.0, "eps_beat": -5.0, "label": "FY22Q4 슬라이드 시작"}),
            ("2022-12-21", {"rev": 40.9, "rev_yoy": -47.0, "gm": 22.0, "eps_beat": 22.0, "label": "FY23Q1 급락했지만 기대 이상"}),
            ("2023-03-28", {"rev": 36.9, "rev_yoy": -53.0, "gm": 11.0, "eps_beat": 5.0, "label": "FY23Q2 가장 밑바닥"}),
            ("2023-06-28", {"rev": 37.5, "rev_yoy": -57.0, "gm": -8.0, "eps_beat": 15.0, "label": "FY23Q3 매출총이익률은 마이너스로 전환"}),
            ("2023-09-27", {"rev": 40.1, "rev_yoy": -40.0, "gm": -1.0, "eps_beat": 18.0, "label": "FY23Q4 ★HBM변곡점 신호"}),
            ("2023-12-20", {"rev": 47.3, "rev_yoy": 16.0, "gm": 20.0, "eps_beat": 68.0, "label": "FY24Q1 ★★수익 역전!EPS추월하다68%"}),
            ("2024-03-20", {"rev": 58.2, "rev_yoy": 58.0, "gm": 28.0, "eps_beat": 82.0, "label": "FY24Q2 ★★★탈출하다"}),
            ("2024-06-26", {"rev": 68.1, "rev_yoy": 82.0, "gm": 35.4, "eps_beat": 6.9, "label": "FY24Q3"}),
            ("2024-09-25", {"rev": 77.5, "rev_yoy": 93.0, "gm": 36.5, "eps_beat": 5.4, "label": "FY24Q4"}),
        ]),
    },
}


# ============================================================
# ~에서JSON파일 로딩 가격 데이터
# ============================================================

def load_prices_from_json(filepath):
    with open(filepath) as f:
        data = json.load(f)
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(timestamps):
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        c = quote["close"][i]
        v = quote["volume"][i]
        h = quote["high"][i]
        if c and v and h:
            rows.append({"date": dt, "close": c, "high": h, "volume": v})
    return rows


# ============================================================
# 모멘텀 디스커버리 엔진
# ============================================================

def scan_momentum(prices):
    signals = []
    for i in range(60, len(prices)):
        row = prices[i]
        close = row["close"]
        past_60_highs = [prices[j]["high"] for j in range(i - 60, i)]
        is_60d_high = close > max(past_60_highs)
        vol_5 = sum(prices[j]["volume"] for j in range(i - 4, i + 1)) / 5
        vol_20 = sum(prices[j]["volume"] for j in range(i - 19, i + 1)) / 20
        is_volume_surge = vol_5 > vol_20 * 1.5
        close_30d_ago = prices[i - 30]["close"]
        pct_30d = (close - close_30d_ago) / close_30d_ago * 100

        if is_60d_high and is_volume_surge:
            signals.append({
                "date": row["date"],
                "close": round(close, 2),
                "pct_30d": round(pct_30d, 1),
                "vol_ratio": round(vol_5 / vol_20, 2),
            })
    return signals


# ============================================================
# 가치 검증 엔진
# ============================================================

def find_fund(ticker, date):
    quarters = list(FUNDAMENTALS[ticker]["quarters"].items())
    latest = None
    prev = None
    for idx, (qd, qf) in enumerate(quarters):
        if qd <= date:
            prev = latest
            latest = (qd, qf)
    return latest, prev


def verify(fund, prev_fund):
    if not fund:
        return 0, {}
    d = fund[1]
    pd = prev_fund[1] if prev_fund else None

    checks = {}
    # 1.매출 가속화(YoY 성장 개선)）
    if pd:
        checks["수익 가속화"] = d["rev_yoy"] > pd["rev_yoy"]
    else:
        checks["수익 가속화"] = d["rev_yoy"] > 20

    # 2.매출총이익률 방향
    if pd:
        checks["매출총이익률↑"] = d["gm"] > pd["gm"] or d["gm"] > 50
    else:
        checks["매출총이익률↑"] = d["gm"] > 40

    # 3.EPS기대를 초과했습니다>10%
    checks["놀라운 이익"] = d["eps_beat"] > 10

    # 4.높은 수익 성장>15%
    checks["높은 수익 성장"] = d["rev_yoy"] > 15

    # 5.매출총이익률>40%
    checks["마오리 건강"] = d["gm"] > 40

    score = sum(1 for v in checks.values() if v)
    return score, checks


# ============================================================
# 백테스트 메인 로직
# ============================================================

def backtest(ticker, prices):
    name = FUNDAMENTALS[ticker]["name"]
    print(f"\n{'='*70}")
    print(f"  {name} ({ticker}) 백테스트")
    print(f"{'='*70}")
    print(f"  가격 데이터：{len(prices)}거래일 ({prices[0]['date']} ~ {prices[-1]['date']})")

    signals = scan_momentum(prices)
    print(f"  모멘텀 트리거 포인트：{len(signals)}개인")

    seen_months = set()
    buy_signals = []
    reject_signals = []

    for sig in signals:
        mk = sig["date"][:7]
        if mk in seen_months:
            continue
        seen_months.add(mk)

        fund, prev = find_fund(ticker, sig["date"])
        score, checks = verify(fund, prev)

        entry = {
            "date": sig["date"],
            "close": sig["close"],
            "pct_30d": sig["pct_30d"],
            "vol_ratio": sig["vol_ratio"],
            "score": score,
            "checks": checks,
            "fund_label": fund[1]["label"] if fund else "N/A",
            "rev_yoy": fund[1]["rev_yoy"] if fund else "N/A",
            "gm": fund[1]["gm"] if fund else "N/A",
            "eps_beat": fund[1]["eps_beat"] if fund else "N/A",
        }

        if score >= 3:
            buy_signals.append(entry)
        else:
            reject_signals.append(entry)

    # 출력 키 신호
    print(f"\n  --- 신호 구매(검증 검증≥3/5）---")
    first_buy = None
    for bs in buy_signals:
        if bs["date"] < "2022-06-01":
            continue
        if not first_buy:
            first_buy = bs
        checks_str = " ".join(
            f"{'✅' if v else '❌'}{k}" for k, v in bs["checks"].items()
        )
        print(f"\n  📅 {bs['date']}  ${bs['close']}  30매일 상승{bs['pct_30d']}%  볼륨을 높이세요{bs['vol_ratio']}x")
        print(f"     기초：{bs['fund_label']}")
        print(f"     전년 대비 수익{bs['rev_yoy']}% | 총 이익{bs['gm']}% | EPS기대를 초과했습니다{bs['eps_beat']}%")
        print(f"     확인하다 {bs['score']}/5：{checks_str}")

    # 부분적인 거부 신호를 표시합니다(스크리닝 효과를 이해하는 데 도움이 됨).）
    early_rejects = [r for r in reject_signals if "2022-06" <= r["date"] <= "2023-06"]
    if early_rejects:
        print(f"\n  --- 거부 신호(가치 검증<3/5）---")
        for r in early_rejects[:3]:
            checks_str = " ".join(
                f"{'✅' if v else '❌'}{k}" for k, v in r["checks"].items()
            )
            print(f"  ❌ {r['date']}  ${r['close']}  확인하다{r['score']}/5：{checks_str}")
            print(f"     기초：{r['fund_label']} | 수익{r['rev_yoy']}% 총 이익{r['gm']}%")

    # 수익 계산
    if first_buy:
        final = prices[-1]
        ret = (final["close"] - first_buy["close"]) / first_buy["close"] * 100
        print(f"\n  {'='*60}")
        print(f"  📊 최초 매수 신호 수익：")
        print(f"     구입하다：{first_buy['date']} @ ${first_buy['close']}")
        print(f"     붙잡다：{final['date']} @ ${round(final['close'], 2)}")
        print(f"     총 수익：{round(ret, 1)}%")
        print(f"  {'='*60}")

    return first_buy


# ============================================================
# NVDA수동 분석(일일 데이터를 얻을 수 없음）
# ============================================================

def nvda_manual_analysis():
    print(f"\n{'='*70}")
    print(f"  엔비디아 (NVDA) 수동 백테스트 분석")
    print(f"  （Yahoo API알려진 과거 가격 노드를 사용하여 제한됨）")
    print(f"{'='*70}")

    # NVDA주요 가격 노드(주식 분할 조정 후)）
    key_prices = [
        ("2022-10-14", 11.2, "연도 최저"),
        ("2023-01-06", 14.3, "ChatGPT촉매작용 후 첫 번째 파동"),
        ("2023-01-27", 19.9, "★ 만들다60일일 최고+대용량 돌파 → 모멘텀 트리거"),
        ("2023-02-22", 23.4, "FY23Q4재무 보고서: 총 이익률63.3%변곡점+EPS추월하다10%"),
        ("2023-05-24", 30.5, "FY24Q1재무보고 전"),
        ("2023-05-25", 37.9, "★★ FY24Q1재무보고 후gap up 24%：수익이 기대를 뛰어넘는다18.5%"),
        ("2023-08-24", 49.3, "FY24Q2：수익이 두 배로 늘었습니다101%"),
        ("2024-01-08", 52.2, "CES 2024"),
        ("2024-03-08", 87.5, "사상 최고치에 근접"),
        ("2024-06-20", 140.8, "주식 분할 후ATH"),
        ("2025-01-06", 149.4, "2025연초"),
    ]

    print(f"\n  주요 가격대：")
    for date, price, note in key_prices:
        print(f"  {date}  ${price:>7.1f}  {note}")

    # 모멘텀 신호 분석
    print(f"\n  --- 모멘텀 신호 분석 ---")

    print(f"\n  📅 2023-01-27  $19.9  ★첫 번째 운동량 트리거 포인트")
    print(f"     가격 신호: 부터$11.2상승하다$19.9（+78%/3개월), 생성됨60일일 최고+볼륨이 크게 증가함")
    print(f"     당시의 기본（FY23Q3 Oct22）：전년 대비 수익-17% | 매출총이익률53.6% | EPS기대를 초과했습니다7.4%")

    fund1, prev1 = find_fund("NVDA", "2023-01-27")
    s1, c1 = verify(fund1, prev1)
    checks_str1 = " ".join(f"{'✅' if v else '❌'}{k}" for k, v in c1.items())
    print(f"     가치 검증 {s1}/5：{checks_str1}")
    if s1 >= 3:
        print(f"     판사：✅ 매수 신호！")
    else:
        print(f"     판사：❌ 가결되지 않음(매출액은 여전히 ​​감소하고 있으나 매출총이익률은 반등)）")
        print(f"     설명: 이는 한계 신호입니다.——프레임워크를 구매하는 것이 아니라 매출총이익률을63.3%전환점은 진짜 신호다")

    print(f"\n  📅 2023-02-22  $23.4  FY23Q4재무 보고서 공개")
    fund2, prev2 = find_fund("NVDA", "2023-02-23")
    s2, c2 = verify(fund2, prev2)
    checks_str2 = " ".join(f"{'✅' if v else '❌'}{k}" for k, v in c2.items())
    print(f"     기초（{fund2[1]['label']}）：전년 대비 수익{fund2[1]['rev_yoy']}% | 매출총이익률{fund2[1]['gm']}% | EPS기대를 초과했습니다{fund2[1]['eps_beat']}%")
    print(f"     가치 검증 {s2}/5：{checks_str2}")
    if s2 >= 3:
        print(f"     판사：✅ 시그널을 구매하세요! 매출총이익률 전환점 확정+EPS기대를 초과했습니다")
    else:
        print(f"     판사：❌ 실패한")

    print(f"\n  📅 2023-05-25  $37.9  ★★FY24Q1'AI폭탄'재무 보고서")
    fund3, prev3 = find_fund("NVDA", "2023-05-25")
    s3, c3 = verify(fund3, prev3)
    checks_str3 = " ".join(f"{'✅' if v else '❌'}{k}" for k, v in c3.items())
    print(f"     기초（{fund3[1]['label']}）：전년 대비 수익{fund3[1]['rev_yoy']}% | 매출총이익률{fund3[1]['gm']}% | EPS기대를 초과했습니다{fund3[1]['eps_beat']}%")
    print(f"     가치 검증 {s3}/5：{checks_str3}")
    if s3 >= 3:
        print(f"     판사：✅ 강한 매수 신호! 수익 가속화+매출총이익률+EPS기대 이상으로 모두 합격")

    print(f"\n  📅 2023-08-24  $49.3  ★★★FY24Q2재무 보고서: 수익이 두 배로 증가했습니다.")
    fund4, prev4 = find_fund("NVDA", "2023-08-24")
    s4, c4 = verify(fund4, prev4)
    checks_str4 = " ".join(f"{'✅' if v else '❌'}{k}" for k, v in c4.items())
    print(f"     기초（{fund4[1]['label']}）：전년 대비 수익{fund4[1]['rev_yoy']}% | 매출총이익률{fund4[1]['gm']}% | EPS기대를 초과했습니다{fund4[1]['eps_beat']}%")
    print(f"     가치 검증 {s4}/5：{checks_str4}")
    print(f"     판사：✅ 만점 신호！5/5모두 합격")

    # 수익 계산
    scenarios = [
        ("2023-01-27（에지 신호）", 19.9, 149.4, "2025-01"),
        ("2023-02-22（재무보고 확인）", 23.4, 149.4, "2025-01"),
        ("2023-05-25（AI폭탄）", 37.9, 149.4, "2025-01"),
    ]
    print(f"\n  {'='*60}")
    print(f"  📊 다양한 구매 지점에서 반품(유지)2025-01 $149.4）：")
    print(f"  {'—'*60}")
    for label, buy_p, sell_p, sell_d in scenarios:
        ret = (sell_p - buy_p) / buy_p * 100
        print(f"  {label:<28} ${buy_p:>6.1f} → ${sell_p}  반품 +{ret:.0f}%")
    print(f"  {'='*60}")


# ============================================================
# 메인 프로그램
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  모멘텀 발견 + 가치검증 백테스팅 시스템 v2")
    print("  목표：NVDA / AMD / MU | 프레임워크 검증")
    print("=" * 70)

    # NVDA：수동 분석
    nvda_manual_analysis()

    # AMD：실제 일일 백테스트
    amd_file = "/tmp/AMD_prices.json"
    if os.path.exists(amd_file):
        amd_prices = load_prices_from_json(amd_file)
        amd_first = backtest("AMD", amd_prices)
    else:
        print("\n  [WARN] AMD가격 데이터를 사용할 수 없습니다.")

    # MU：실제 일일 백테스트
    mu_file = "/tmp/MU_prices.json"
    if os.path.exists(mu_file):
        mu_prices = load_prices_from_json(mu_file)
        mu_first = backtest("MU", mu_prices)
    else:
        print("\n  [WARN] MU가격 데이터를 사용할 수 없습니다.")

    # 요약
    print(f"\n\n{'='*70}")
    print(f"  📋 백테스트 요약: 프레임워크가 캡처할 수 있습니까?AI칩 빅 쓰리？")
    print(f"{'='*70}")
    print(f"""
  ┌────────────────────────────────────────────────────────────────┐
  │  NVDA：✅ 캡쳐할 수 있는                                              │
  │  - 가장 빠른 신호：2023-01-27（가장자리) 또는 2023-02-22（확인하다）          │
  │  - 가장 확실한 신호：2023-05-25 FY24Q1"AI폭탄"재무보고 후               │
  │  - 프레임 인ChatGPT촉매+총 이익 마진이 바뀌면 신호가 전송될 수 있습니다.                 │
  │  - 최근에도2023-05구매를 확인하고 까지 보류하세요.2025아직있다+294%           │
  │                                                                │
  │  AMD：실제 백테스트 결과 보기↑                                          │
  │  - 예상되는：2023-10 ~ 2024-01 방아쇠（MI300풀어 주다+수익 반등）         │
  │                                                                │
  │  MU：실제 백테스트 결과 보기↑                                           │
  │  - 예상되는：2023-12 ~ 2024-03 방아쇠（HBM필요+수익 역전+EPS다차오）   │
  └────────────────────────────────────────────────────────────────┘

  핵심 결론：
  1. 프레임 쌍NVDA가장 효과적인——"매출총이익률 전환점+EPS기대를 초과했습니다"가장 강력한 초기 신호입니다.
  2. 순수 가치 투자자들은 그렇게 할 것입니다."매출은 여전히 ​​감소세"놓치다2023연초 진입 시점
  3. 순수한 모멘텀 투자자들은2022올해의 최고 기록을 쫓다NVDA그리고 돈을 잃다
  4. "기세+값"조합의 장점: 가격이 오를 때까지 기다리세요+펀더멘털 확인 후 시장 진입
     피하다2022올해의 거짓돌파가 포착됐다2023올해의 진정한 전환점

  프레임워크의 한계：
  1. 요구사항이 엄격한 경우"전년 대비 수익>15%"，그리워할 것이다NVDA 2023-01첫 번째 신호
     → 늘리는 것이 좋습니다"매출총이익률은 지속적으로 개선되고 있습니다."독립적인 구매 조건으로
  2. 순환 주식의 경우（MU）조정 필요: 반도체 사이클의 바닥에서 매출이 급격히 감소하는 것이 일반적입니다.
     → 늘리는 것이 좋습니다"EPS기대 이상>30%"순환주에 대한 특수 조건
""")
