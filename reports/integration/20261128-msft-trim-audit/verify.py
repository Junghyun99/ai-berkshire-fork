"""MSFT 첫 축소 결정 1건. 원시 종가에 배당 권리를 한 번만 더한다."""
from decimal import Decimal as D

sale = D("540.22")
trigger = D("511")
assert D("531.01") >= trigger and sale >= trigger
# 해당 결정으로 줄어든 1주의 가치를 같은 1주를 보유한 경우와 대조한다.
closes = dict(line.split() for line in """10-29 530.14
10-30 521.91
11-02 507.12
11-03 520.99
11-04 555.80
11-05 535.93
11-06 530.61
11-09 545.18
11-10 533.16
11-11 521.12
11-12 523.00
11-13 523.88
11-16 517.99
11-17 506.24
11-18 508.29
11-19 498.30""".splitlines())
delta = {day: sale - D(close) - (D("0.98") if day == "11-19" else 0)
         for day, close in closes.items()}
assert min(delta, key=delta.get) == "11-04" and min(delta.values()) == D("-15.58")
assert delta["11-19"] == D("40.94")
for day in ("11-04", "11-19"):
    print(day, "USD/주", delta[day], "3주 최초 평가액 대비 %p",
          round(100 * delta[day] / (3 * sale), 4))
print("매도 비용 0.25% 적용 후 달러 차이", delta["11-19"] - sale * D("0.0025"))
