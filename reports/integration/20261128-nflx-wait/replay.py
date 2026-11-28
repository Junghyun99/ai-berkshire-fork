"""2026년 11월, 미 달러 100 기준. 정규장 원시 시가·저가·종가."""
from decimal import Decimal as D

rows = []
for line in """2 62.20 61.71 62.34
3 62.68 61.90 63.42
4 64.55 64.02 66.39
5 67.29 64.67 65.56
6 63.86 63.31 63.41
9 63.30 62.95 63.95
10 63.46 62.60 63.26
11 62.84 62.75 64.54
12 64.27 62.55 62.69
13 62.88 62.12 62.15
16 62.89 60.48 60.75
17 60.56 59.41 59.68
18 59.70 59.42 59.82
19 59.92 58.18 58.46
20 58.34 56.56 56.73""".splitlines():
    day, op, low, close = line.split()
    rows.append((int(day), D(op), D(low), D(close)))

limit = D("59.50")
touch = next(day for day, _, low, _ in rows if low <= limit)
signal = next(day for day, _, _, close in rows if close <= limit)
entry = next(day for prev, (day, op, _, _) in zip(rows, rows[1:])
             if prev[3] <= limit and op <= limit)
assert (touch, signal, entry) == (17, 19, 20)
assert all(low > D("52.50") for _, _, low, _ in rows)

def outcomes(entry_day, fee, rate):
    nav = [D(100)]
    shares = None
    for day, op, _, close in rows:
        cash = 100 * (1 + rate * (day-2) / 365)
        if day == entry_day:
            shares = cash / (op * (1 + fee))
        nav.append(cash if shares is None else shares * close)
    mdd = min(v/max(nav[:i+1])-1 for i,v in enumerate(nav))
    return nav[-1], 100*mdd

for fee, rate in [(D(".0025"), D(0)), (D(0), D(0)), (D(".0025"), D(".04"))]:
    for label, day in [("즉시",2), ("대기",entry), ("현금",None)]:
        value, mdd = outcomes(day, fee, rate)
        print(f"{fee=} {rate=} {label}: 기말 {value:.4f}, 수익률 {value-100:.4f}%, MDD {mdd:.4f}%")
