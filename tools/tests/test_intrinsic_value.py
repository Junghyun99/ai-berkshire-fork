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
        self.assertEqual(iv.growth_scenarios(112), (0.0, 15.0, 15.0))  # 중립도 상한 15%
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


class ManualInputTest(unittest.TestCase):
    def write(self, d, obj):
        import json
        path = os.path.join(d, "valuation-inputs.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return path

    def test_load_inputs_validation(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(iv.load_inputs(os.path.join(d, "none.json")), {})
            with self.assertRaises(SystemExit):
                iv.load_inputs(self.write(d, {"출처": []}))                       # 출처 필수
            with self.assertRaises(SystemExit):
                iv.load_inputs(self.write(d, {"출처": ["x"], "유형": "D"}))        # 유형 지정엔 사유
            with self.assertRaises(SystemExit):
                iv.load_inputs(self.write(d, {"출처": ["x"], "재무": {}}))         # 재무엔 통화
            self.assertEqual(iv.load_inputs(self.write(d, {"출처": ["x"], "유형": "D", "유형사유": "지주"}))["유형"], "D")

    def test_sotp(self):
        d = {"구성": [{"이름": "자회사A", "지분율": 0.5, "가치": [100, 200, 300]},
                      {"이름": "자회사B", "지분율": 1.0, "가치": [50, 50, 50]}], "본사순현금": 10, "지주할인": [30, 15, 0]}
        v = iv.sotp_values(d, 10)
        self.assertAlmostEqual(v[0], (50 + 50 + 10) * 0.7 / 10)
        self.assertAlmostEqual(v[1], (100 + 50 + 10) * 0.85 / 10)
        self.assertAlmostEqual(v[2], (150 + 50 + 10) / 10)
        d.pop("지주할인")
        self.assertAlmostEqual(iv.sotp_values(d, 10)[2], 21.0)         # 기본 할인 (30, 15, 0)

    def test_explicit_dcf(self):
        # 성장 0·마진 고정·재투자 0이면 FCF 고정 → 도달연도 N 이후 영구성장 1/2/3% 영구연금
        e = {"기준매출": 1000, "현재영업이익률": 10, "매출성장": [0, 0, 0], "목표영업이익률": [10, 10, 10],
             "도달연도": 5, "재투자율": [0, 0, 0], "세율": 0}
        v = iv.explicit_dcf(e, 10, 0, 1)
        self.assertAlmostEqual(v[1], iv.dcf_value(100, 0, 2, 10), places=6)
        self.assertLess(v[0], v[1])
        self.assertLess(v[1], v[2])

    def test_evaluate_manual_market_with_cycle_pe(self):
        rev = {y: 1000.0 for y in range(2016, 2026)}
        op = {y: (50.0 if y % 2 else 150.0) for y in range(2016, 2026)}            # 하락 66.7% → B
        inp = {"출처": ["유가증권보고서"], "통화": "JPY", "시장": "JP", "시장PER": 15, "주식수": 10, "현금": 100, "차입금": 0,
               "재무": {str(y): {"rev": rev[y], "op": op[y], "ni_own": op[y] * 0.7, "eq_own": 1000, "ocf": op[y],
                                 "capex": 10} for y in rev}}
        res = iv.evaluate("6871.T", "2026-10-31", "JPY", inputs=inp)
        self.assertEqual(res["유형"], "B")
        self.assertEqual(res["근거"]["PER"], [9.0, 12.0, 15.0])
        # 중립: 1000 × 10% × (1 − 22%) × 12 + 100 = 1036 → /10
        self.assertAlmostEqual(res["시나리오"]["중립"], 103.6)
        del inp["시장PER"]
        self.assertIsNone(iv.evaluate("6871.T", "2026-10-31", "JPY", inputs=inp)["시나리오"])   # JP 기준 PER 없음

    def test_currency_conversion_with_adr(self):
        inp = {"출처": ["x"], "통화": "CNY", "시장": "US", "주식수": 4, "현금": 0, "차입금": 0, "유형": "D", "유형사유": "테스트",
               "D": {"구성": [{"이름": "a", "지분율": 1, "가치": [400, 400, 400]}], "지주할인": [0, 0, 0]},
               "재무": {"2025": {"rev": 1}}}
        iv._FX_CACHE[("CNY", "2026-11-25")] = 0.14
        res = iv.evaluate("PDD", "2026-11-25", "USD", inputs=inp)       # 주당 100 CNY × 0.14 × ADR 4
        self.assertAlmostEqual(res["시나리오"]["중립"], 56.0)
        self.assertEqual(res["통화"], "USD")
        res = iv.evaluate("XYZ", "2026-11-25", "USD", inputs=inp)       # ADR 비율 없음 → 비교 불가
        self.assertTrue(res.get("통화불일치"))
        self.assertIsNone(res["시나리오"])


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

            def fake(ticker, as_of, cur, name=""):
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
