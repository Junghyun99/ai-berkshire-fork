"""내재가치 표준 산식 오프라인 테스트 — 순수 함수와 원장 비교(가짜 평가기).

실행: python3 -m unittest discover -s tools/tests -v
"""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import intrinsic_value as iv  # noqa: E402


class PureTest(unittest.TestCase):
    def test_cagr(self):
        s = {2016: 100, 2021: 161.051}                       # 5년 10%
        s.update({y: 120 for y in (2017, 2018, 2019, 2020)})
        self.assertAlmostEqual(iv.cagr(s), 10.0, places=3)
        self.assertIsNone(iv.cagr({2020: 1, 2021: 2, 2022: 3}))   # 5개 해 미만
        self.assertIsNone(iv.cagr({2016: -1, 2017: 1, 2018: 1, 2019: 1, 2020: 2}))

    def test_growth_scenarios(self):
        self.assertEqual(iv.growth_scenarios(10), (0.0, 5.0, 10.0))
        self.assertEqual(iv.growth_scenarios(20), (0.0, 10.0, 15.0))   # 낙관 상한 15%
        self.assertEqual(iv.growth_scenarios(-4), (-4.0, -2.0, 0.0))

    def test_dcf_value(self):
        # 성장 0, 영구성장 0 이면 영구연금 = CF / r
        self.assertAlmostEqual(iv.dcf_value(100, 0, 0, 10), 1000.0, places=6)
        # 1단계 성장이 있으면 커진다, 할인율 ≤ 영구성장률은 거부
        self.assertGreater(iv.dcf_value(100, 10, 2, 9), iv.dcf_value(100, 0, 2, 9))
        with self.assertRaises(ValueError):
            iv.dcf_value(100, 0, 9, 9)

    def test_margin_roe_pbr_label(self):
        self.assertEqual(iv.margin_scenarios([1, 2, 3, 4, 5, 6]), (2.0, 3.5, 5.0))
        roe = iv.roe_series({2024: 10, 2025: 12}, {2023: 90, 2024: 110, 2025: 130})
        self.assertAlmostEqual(roe[2024], 10.0)               # 10 / 평균(90, 110)
        self.assertAlmostEqual(roe[2025], 10.0)               # 12 / 평균(110, 130)
        self.assertAlmostEqual(iv.justified_pbr(10, 10), 1.0)  # ROE = COE → PBR 1
        self.assertAlmostEqual(iv.justified_pbr(14, 10), 1.5)
        self.assertEqual(iv.justified_pbr(1, 10), 0.0)          # ROE < g → 0
        self.assertEqual(iv.label_range(80, 100, 140), (90.0, 120.0))

    def test_cycle_pe_by_market(self):
        self.assertEqual(iv.cycle_pe("US"), (9.6, 12.8, 16.0))
        self.assertEqual(iv.cycle_pe("KR"), (6.0, 8.0, 10.0))

    def test_classify(self):
        dd = lambda x, n=10: {"하락률": x, "연도수": n}  # noqa: E731
        self.assertEqual(iv.classify(True, dd(80), 10), "C")
        self.assertEqual(iv.classify(False, dd(50), 10), "B")
        self.assertEqual(iv.classify(False, dd(100, 3), 10), "A")   # 이력 부족이면 경기순환으로 단정하지 않음
        self.assertEqual(iv.classify(False, dd(20), -1), "E")
        self.assertEqual(iv.classify(False, dd(20), None), "E")
        self.assertEqual(iv.classify(False, dd(20), 5), "A")


class LedgerCompareTest(unittest.TestCase):
    def test_compare_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id", "기록일", "종목", "티커", "통화", "판단", "기록시점가", "내재가치하단", "내재가치상단"])
                w.writerow(["a1", "2026-10-01", "가", "AAA", "USD", "관망", "100", "100", "140"])
                w.writerow(["a2", "2026-11-01", "가", "AAA", "USD", "관망", "70", "100", "140"])   # 최신만 비교
                w.writerow(["b", "2026-11-01", "나", "BBB", "USD", "관망", "50", "80", "120"])

            def fake(ticker, as_of, cur):
                if ticker == "BBB":
                    raise ConnectionError("down")
                return {"유형": "A", "주식수": 10, "순현금": 0, "경고": [], "시나리오": {"비관": 80, "중립": 100, "낙관": 140},
                        "범위": (90.0, 120.0)}
            mos = [{"id": "a2", "U_e": "5", "L": "0"}]
            rows = {r["종목"]: r for r in iv.ledger_compare(path, "2026-11-27", fake, mos)}
        a = rows["가"]
        self.assertEqual((a["id"], a["공식중앙"], a["공식/분석가"]), ("a2", 105.0, 0.875))
        self.assertEqual((a["U_v공식"], a["요구안전마진공식"], a["현재안전마진공식"], a["상태공식"]),
                         (14.3, 24.3, 33.3, "A 요구 충족"))
        self.assertIn("계산 실패", rows["나"]["비고"])


if __name__ == "__main__":
    unittest.main()
