"""신규 편입 전후의 주식 예산 대비 시나리오 손실(%p)을 재현한다."""
from decimal import Decimal as D


def loss(weights, shocks):
    return sum(w * shocks[t] / 100 for t, w in weights.items())


def compare(existing, candidate, target, cash, shocks, budget):
    if candidate in existing or min(target, cash, budget, *existing.values()) < 0:
        raise ValueError("신규 후보와 음수가 아닌 비중·예산이 필요합니다")
    if min(shocks.values()) < 0 or sum(existing.values()) + cash > 100:
        raise ValueError("손실률 또는 예산 입력을 확인하세요")
    before = loss(existing, shocks)
    full = min(target, cash)
    impact = shocks[candidate] / 100
    room = max(D(0), budget - before)
    allowed = min(full, room / impact) if impact else full
    return before, full, before + full * impact, allowed, before + allowed * impact


if __name__ == "__main__":
    existing = {"NVDA": D(4), "TXN": D(4)}
    for shock in (10, 20, 30):
        shocks = {"NVDA": D(30), "TXN": D(shock), "AVGO": D(30)}
        print(shock, *compare(existing, "AVGO", D(4), D(4), shocks, D("2.5")))
