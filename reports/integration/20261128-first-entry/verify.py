"""어도비 사례의 조건부 첫 편입액 검산. 모든 금액은 원."""
from decimal import Decimal as D


def first_amount(price, requested, cap, held=0, cash=500_000, tranche_open=True):
    if D(price) > D("250.00") or not tranche_open:
        return 0
    return max(0, min(requested, cap - held, 100_000 - held, cash))


if __name__ == "__main__":
    for cap, requested in [(400_000, 400_000), (500_000, 100_000),
                           (60_000 / D("0.30"), 200_000)]:
        assert first_amount("250.23", requested, cap) == 0
        assert first_amount("250.00", requested, cap) == 100_000
        assert first_amount("250", requested, cap, held=60_000) == 40_000
        assert first_amount("250", requested, cap, held=110_000) == 0
        assert first_amount("250", requested, cap, cash=30_000) == 30_000
        assert first_amount("250", requested, cap, tranche_open=False) == 0
    print("세 방식의 가격 경계·보유액·현금·차수 상태 검산 통과")
