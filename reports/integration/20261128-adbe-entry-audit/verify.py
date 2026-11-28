"""main 반영 이후 가격 조건과 두 모의 규칙의 USD 가격수익률을 재현한다."""
from decimal import Decimal as D

# 미국 거래일, ADBE 시가·종가, SPY 시가. Stock Analysis 원시 USD 가격.
bars = [
    ("2026-11-04", D("248.30"), D("248.48"), D("762.99")),
    ("2026-11-05", D("250.59"), D("246.44"), D("765.47")),
    ("2026-11-06", D("239.00"), D("239.30"), D("734.82")),
]
limit = D(250)
end_adbe, end_spy = D("234.79"), D("728.32")  # 11월 27일 정규장 종가


def first_entry(require_close):
    for i, bar in enumerate(bars):
        if require_close and (i == 0 or bars[i-1][2] > limit):
            continue
        if bar[1] <= limit:
            return bar
    raise ValueError("관측 범위 안에 충족일 없음")


for close_rule, expected in [(False, "2026-11-04"), (True, "2026-11-06")]:
    day, adbe, _, spy = first_entry(close_rule)
    assert day == expected
    returns = [(end / start - 1) * 100 for start, end in [(adbe, end_adbe), (spy, end_spy)]]
    print(day, *(f"{v:.3f}" for v in [*returns, returns[0] - returns[1]]))
