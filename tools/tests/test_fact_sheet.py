"""팩트시트 오프라인 테스트 — Yahoo·네이버·DART·SEC 응답을 픽스처로 대체.

실행: python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import _us_common  # noqa: E402
import fact_sheet as fs  # noqa: E402
import global_stock_data  # noqa: E402


def meta(cur="KRW", price=100.0):
    return {"longName": "테스트", "currency": cur, "regularMarketPrice": price, "regularMarketTime": 1793082603,
            "gmtoffset": 32400, "fiftyTwoWeekHigh": 120.0, "fiftyTwoWeekLow": 80.0, "fullExchangeName": "KSE"}


def series(fin_cur="KRW", price_cur="KRW", shares=1_000.0, mcap=100_000.0):
    def annual(vals):
        return [(f"{y}-12-31", v, fin_cur) for y, v in zip((2023, 2024, 2025), vals)]
    return {
        "annualTotalRevenue": annual([1000.0, 1100.0, 1200.0]),
        "annualOperatingIncome": annual([100.0, 110.0, 120.0]),
        "annualNetIncomeCommonStockholders": annual([80.0, 90.0, 96.0]),
        "annualDilutedEPS": annual([0.08, 0.09, 0.096]),
        "annualStockholdersEquity": annual([800.0, 900.0, 960.0]),
        "annualOperatingCashFlow": annual([120.0, 130.0, 144.0]),
        "annualCapitalExpenditure": annual([-40.0, -40.0, -44.0]),
        "annualFreeCashFlow": annual([80.0, 90.0, 100.0]),
        "quarterlyShareIssued": [("2026-06-30", shares, "")],
        "trailingMarketCap": [("2026-10-26", mcap, price_cur)],
        "trailingPeRatio": [("2026-10-26", 10.4, "")],
        "trailingPbRatio": [("2026-10-26", 1.04, "")],
    }


class FactSheetTest(unittest.TestCase):
    def patch(self, target, name, **kw):
        p = mock.patch.object(target, name, **kw)
        p.start()
        self.addCleanup(p.stop)

    def test_korea_ratios_mcap_check_and_missing_dart_key(self):
        self.patch(global_stock_data, "_resolve", return_value=("005930.KS", meta()))
        self.patch(fs, "yahoo_series", return_value=series())
        self.patch(global_stock_data, "_naver_market_cap", return_value=100_500.0)
        with mock.patch.dict(os.environ, {"DART_API_KEY": ""}):
            sheet = fs.collect("005930")
        last = sheet["annual"][-1]
        self.assertAlmostEqual(last["영업이익률"], 10.0)
        self.assertAlmostEqual(last["ROE"], 10.0)
        self.assertAlmostEqual(last["영업CF/순이익"], 1.5)
        checks = {c["항목"]: c for c in sheet["checks"]}
        self.assertEqual(checks["시가총액 검산(주가×주식수)"]["판정"], "✅")   # 100×1000 = 100,000
        self.assertEqual(checks["시가총액"]["판정"], "✅")                   # 네이버 대비 0.5%
        self.assertTrue(any("DART_API_KEY" in w for w in sheet["warnings"]))
        out = fs.render(sheet)
        self.assertIn("현재 시점 스냅샷", out)
        self.assertIn("두 값을 맞춘 숫자를 지어내지 않는다", out)

    def test_currency_mismatch_warns(self):
        self.patch(global_stock_data, "_resolve", return_value=("0700.HK", meta("HKD")))
        self.patch(fs, "yahoo_series", return_value=series(fin_cur="CNY", price_cur="HKD"))
        sheet = fs.collect("0700")
        self.assertEqual((sheet["price_currency"], sheet["financial_currency"]), ("HKD", "CNY"))
        self.assertTrue(any("통화" in w and "CNY" in w for w in sheet["warnings"]))
        out = fs.render(sheet)
        self.assertIn("주가 통화 HKD · 재무 통화 CNY", out)
        self.assertIn("0.10 CNY", out)  # EPS 는 재무 통화로 표기

    def test_dart_cross_check_grades(self):
        self.patch(global_stock_data, "_resolve", return_value=("005930.KS", meta()))
        self.patch(fs, "yahoo_series", return_value=series())
        self.patch(global_stock_data, "_naver_market_cap", return_value=None)
        import dart_data
        self.patch(dart_data, "_resolve", return_value=("00126380", "삼성전자"))
        self.patch(dart_data, "_fetch_financials", return_value=[{}])
        self.patch(dart_data, "_extract_accounts", return_value={
            "매출액": {"thstrm": 1200.0}, "영업이익": {"thstrm": 125.0},
            "지배주주순이익": {"thstrm": 96.5}, "영업활동현금흐름": {"thstrm": 160.0}})
        with mock.patch.dict(os.environ, {"DART_API_KEY": "x"}):
            sheet = fs.collect("005930")
        got = {c["항목"]: c["판정"] for c in sheet["checks"] if c["기준출처"] == "DART(연결)"}
        self.assertEqual(got, {"매출": "✅", "영업이익": "⚠️", "지배순이익": "✅", "영업CF": "❌"})

    def test_sec_unavailable_is_warning_not_failure(self):
        self.patch(global_stock_data, "_resolve", return_value=("AAPL", meta("USD")))
        self.patch(fs, "yahoo_series", return_value=series("USD", "USD"))
        import sec_edgar_data
        self.patch(sec_edgar_data, "_load_us_gaap", side_effect=_us_common.UnavailableError("HTTP 403"))
        sheet = fs.collect("AAPL")
        self.assertTrue(any("SEC EDGAR 조회 실패" in w for w in sheet["warnings"]))
        self.assertTrue(sheet["annual"])

    def test_unknown_symbol_is_no_data(self):
        self.patch(global_stock_data, "_resolve", return_value=(None, None))
        with self.assertRaises(_us_common.NoDataError):
            fs.collect("ZZZZ")

    def test_missing_values_render_as_no_data_not_zero(self):
        self.patch(global_stock_data, "_resolve", return_value=("005930.KS", meta()))
        data = series()
        data["annualOperatingIncome"] = []
        self.patch(fs, "yahoo_series", return_value=data)
        self.patch(global_stock_data, "_naver_market_cap", return_value=None)
        with mock.patch.dict(os.environ, {"DART_API_KEY": ""}):
            sheet = fs.collect("005930")
        self.assertIsNone(sheet["annual"][-1]["영업이익률"])
        self.assertIn("데이터 없음", fs.render(sheet))

    def test_grade_thresholds(self):
        self.assertEqual(fs.grade(100, 100.9)[1], "✅")
        self.assertEqual(fs.grade(100, 104)[1], "⚠️")
        self.assertEqual(fs.grade(100, 110)[1], "❌")
        self.assertEqual(fs.grade(None, 1)[1], "비교 불가")


if __name__ == "__main__":
    unittest.main()
