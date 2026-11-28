"""같은 MSFT 1주에서 출발하는 세 안의 USD 평가액과 최대낙폭."""
from decimal import Decimal as D

initial, buy = D("525.69"), D("239")
# 11월 관측일과 조정 전 정규장 종가
closes = [(6,"530.61","239.30"),(9,"545.18","237.32"),(10,"533.16","236.70"),
          (11,"521.12","237.60"),(12,"523.00","238.54"),(13,"523.88","243.08"),
          (16,"517.99","246.00"),(17,"506.24","235.55"),(18,"508.29","226.20"),
          (19,"498.30","221.68")]
assert D("535.93") >= 511 and D("246.44") <= 250
assert initial >= 511 and buy <= 250
for fee in (D("0.0025"), D(0)):
    proceeds = initial * (1-fee)
    shares = proceeds / (buy * (1+fee))
    paths = [[initial] for _ in range(3)]
    for day, msft, adbe in closes:
        paths[0].append(D(msft) + (D("0.98") if day == 19 else 0))
        paths[1].append(proceeds * (1+D("0.0417")*(day-6)/365))
        paths[2].append(shares * D(adbe))
    for path in paths:
        drawdown = min(x/max(path[:i+1])-1 for i,x in enumerate(path))
        print(f"{path[-1]:.4f} USD, return {(path[-1]/initial-1)*100:.4f}%, MDD {100*drawdown:.4f}%")
    hold, cash, switch = [p[-1] for p in paths]
    assert abs((cash-hold)+(switch-cash)-(switch-hold)) < D("1e-20")
    print("매도·매수·교체 기여 USD:", *(round(v, 4) for v in (cash-hold,switch-cash,switch-hold)))
