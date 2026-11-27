"""같은 현금을 둔 대조군으로 단일 보유기간의 비용 차감 전 성과 차이를 분해한다."""
from fractions import Fraction as F


def compare(returns, cash_return, withheld):
    """수익률·비중은 % 단위, 결과는 전체 주식 예산 대비 %p 단위."""
    if len(returns) != 3 or not 0 <= withheld <= 4:
        raise ValueError("기존 두 기업과 신규 한 곳, 감액 범위 0~4가 필요합니다")
    withheld, cash_return = F(withheld), F(cash_return)
    mean = sum(map(F, returns)) / 3
    full = 12 * mean / 100
    matched = ((12 - withheld) * mean + withheld * cash_return) / 100
    selected = full + withheld * (cash_return - returns[2]) / 100
    return full, selected, matched


if __name__ == "__main__":
    for scenario in [(-30, -10, -30), (-30, -30, -30), (-30, -10, 30)]:
        full, selected, matched = compare(scenario, 0, F(1))
        print(scenario, *(f"{float(x):+.4f}" for x in
                          (full, selected, matched, matched-full, selected-matched)))
