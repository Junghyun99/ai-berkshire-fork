"""가상 단일 시점의 제안 재현. 단위는 만 원."""
from pathlib import Path
from runpy import run_path

BASE = Path(__file__).resolve().parents[1]
allocate = run_path(str(BASE / "20261128-simultaneous-sizing/compare.py"))["allocate"]
before = {"A": 0, "B": 10, "C": 50, "기타": 925, "현금": 15}
# 가격·사업 조건을 확인한 미사용 차수만 입력한다. 현금은 여기서 차감하지 않는다.
requests = {"A": min(10, 40 - before["A"]), "B": min(15, 50 - before["B"])}
assert requests == {"A": 10, "B": 15}
for label, rule, sale, expected in [
    ("비례", "proportional", 0, (6, 19, 50, 0)),
    ("A 우선", "priority", 0, (10, 15, 50, 0)),
    ("C 일부 교체", "proportional", 10, (10, 25, 40, 0)),
]:
    assert 0 <= sale <= before["C"]
    cash = before["현금"] + sale
    buys = allocate(requests, cash, rule, {"A": 1, "B": 2})
    after = dict(before)
    for name, amount in buys.items():
        assert 0 <= amount <= requests[name]
        after[name] += amount
    after["C"] -= sale
    after["현금"] = cash - sum(buys.values())
    assert tuple(after[k] for k in ("A", "B", "C", "현금")) == expected
    assert min(after.values()) >= 0 and sum(after.values()) == sum(before.values()) == 1000
    print(label, expected, "B+C", after["B"] + after["C"])
