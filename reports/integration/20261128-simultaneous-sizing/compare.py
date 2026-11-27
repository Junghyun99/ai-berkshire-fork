"""분할 가능한 이론 금액으로 동시 후보의 현금 배정을 비교한다."""
from fractions import Fraction as F


def allocate(requests, cash, method, ranks=None):
    amounts = {name: F(value) for name, value in requests.items()}
    cash = F(cash)
    if cash < 0 or any(v < 0 for v in amounts.values()):
        raise ValueError("금액은 0 이상이어야 합니다")
    if method not in ("equal", "proportional", "priority"):
        raise ValueError("알 수 없는 배정 방식")
    if method == "priority" and (ranks is None or set(ranks) != set(amounts)):
        raise ValueError("모든 후보에 사전 순위가 필요합니다")
    result = dict.fromkeys(amounts, F(0))
    remaining = min(cash, sum(amounts.values()))
    if method == "equal":
        pending = sorted(amounts, key=amounts.get)
        for i, name in enumerate(pending):
            result[name] = min(amounts[name], remaining / (len(pending) - i))
            remaining -= result[name]
        return result
    tiers = ranks if method == "priority" else dict.fromkeys(amounts, 0)
    for rank in sorted(set(tiers.values())):
        group = [n for n in amounts if tiers[n] == rank]
        demand = sum(amounts[n] for n in group)
        available = min(remaining, demand)
        if demand:
            for name in group:
                result[name] = available * amounts[name] / demand
        remaining -= available
    return result


if __name__ == "__main__":
    requests = {"A": 10, "B": 30, "C": 60}
    for rule in ("equal", "proportional", "priority"):
        allocation = allocate(requests, 60, rule, {"C": 1, "B": 2, "A": 3})
        print(rule, {n: str(v) for n, v in allocation.items()})
