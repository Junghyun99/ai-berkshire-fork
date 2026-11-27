"""어도비 §7에서 선택한 두 추가 차수와 첫 축소선을 검산하는 연구 사례."""
import unittest
from decimal import Decimal as D


def review(price, *, shares_value=100_000, cash=200_000, before_event=False,
           growth=None, arr=None, other_breach=False, second_open=False,
           fourth_open=True, trim_reviewed=False):
    """분모 1,000만원, 상한 5%, 1차 완료·3차 미해당이라는 사례에 한정."""
    if other_breach or (growth is not None and growth < 7) or (arr is not None and arr < 8):
        return "반증 재검토", 0
    if D(price) >= 380 and not trim_reviewed:
        return "가격 축소 검토", 0
    if not before_event and (growth is None or arr is None):
        return "자료 대기", 0
    limit = 100_000 if before_event else 500_000
    request = 0
    if second_open and D(price) <= 235:
        request = 100_000
    elif fourth_open and not before_event and D(price) <= D("274.12"):
        request = 150_000
    amount = max(0, min(request, cash, limit - shares_value))
    return ("추가 검토", amount) if amount else ("유지", 0)


class HoldingReviewTest(unittest.TestCase):
    def test_lower_price_with_full_event_budget(self):
        self.assertEqual(review("235", before_event=True, second_open=True), ("유지", 0))

    def test_same_price_different_evidence(self):
        self.assertEqual(review("274.12", growth=7, arr=8), ("추가 검토", 150_000))
        self.assertEqual(review("274.12", growth=7), ("자료 대기", 0))
        self.assertEqual(review("274.12", growth=7, arr=7.9), ("반증 재검토", 0))

    def test_caps_and_used_tranche(self):
        self.assertEqual(review("274.12", shares_value=450_000, growth=7, arr=8)[1], 50_000)
        self.assertEqual(review("274.12", cash=15_000, growth=7, arr=8)[1], 15_000)
        self.assertEqual(review("274.12", fourth_open=False, growth=7, arr=8), ("유지", 0))

    def test_independent_trim_reasons(self):
        self.assertEqual(review("380", growth=7, arr=8), ("가격 축소 검토", 0))
        self.assertEqual(review("235", growth=7, arr=8, other_breach=True), ("반증 재검토", 0))
        self.assertEqual(review("380", growth=7, arr=8, trim_reviewed=True), ("유지", 0))
