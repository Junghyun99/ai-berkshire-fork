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
        self.patch(dart_data, "share_counts", return_value=None)
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

    def test_zero_price_is_no_data(self):
        m = meta()
        m["fiftyTwoWeekLow"] = 0.0
        self.patch(global_stock_data, "_resolve", return_value=("005930.KS", m))
        self.patch(fs, "yahoo_series", return_value=series())
        self.patch(global_stock_data, "_naver_market_cap", return_value=None)
        with mock.patch.dict(os.environ, {"DART_API_KEY": ""}):
            sheet = fs.collect("005930")
        self.assertIsNone(sheet["snapshot"]["52주 최저"]["value"])
        self.assertIn("| 52주 최저 | 데이터 없음 |", fs.render(sheet))

    def _korea_with_shares(self, pref_found, yahoo_shares=1_000.0, basis=True):
        """보통주 1,000주(자기주식 100), 우선주 200주, 보통주 100원, Yahoo 주식수는 인자로."""
        self.patch(global_stock_data, "_resolve", side_effect=lambda c: (
            ("005930.KS", meta()) if c == "005930" else
            ((f"{c}.KS", meta(price=50.0)) if c in pref_found else (None, None))))
        data = series(shares=yahoo_shares)
        if basis:
            data["trailingNetIncomeCommonStockholders"] = [("2026-06-30", 110.0, "KRW")]
            data["quarterlyStockholdersEquity"] = [("2026-06-30", 1_100.0, "KRW")]
        self.patch(fs, "yahoo_series", return_value=data)
        self.patch(global_stock_data, "_naver_market_cap", return_value=100_000.0)
        self.patch(fs, "_naver_number", return_value=1.0)
        import dart_data
        self.patch(dart_data, "_resolve", return_value=("00126380", "삼성전자"))
        self.patch(dart_data, "_fetch_financials", return_value=None)
        self.patch(dart_data, "share_counts", return_value={
            "기준일": "2026-06-30", "보고서": "반기보고서 (2026.06)", "접수번호": "1",
            "보통주": {"발행": 1_000.0, "자기주식": 100.0, "유통": 900.0},
            "우선주": {"발행": 200.0, "자기주식": 0.0, "유통": 200.0}})
        with mock.patch.dict(os.environ, {"DART_API_KEY": "x"}):
            return fs.collect("005930")

    def test_preferred_shares_in_per_share_metrics(self):
        sheet = self._korea_with_shares({"005935"})
        snap = {k: v["value"] for k, v in sheet["snapshot"].items()}
        self.assertEqual(snap["유통주식수(보통+우선)"], 1_100.0)
        self.assertEqual(snap["우선주 현재가"], 50.0)
        self.assertAlmostEqual(snap["시가총액(보통+우선, 유통주식)"], 100 * 900 + 50 * 200)   # 100,000
        self.assertAlmostEqual(snap["EPS(보통+우선 유통주식)"], 110.0 / 1_100)              # TTM 순이익
        self.assertAlmostEqual(snap["BPS(보통+우선 유통주식)"], 1.0)                        # 최근 분기 자본
        self.assertAlmostEqual(snap["PER(우선주 포함)"], 100_000 / 110.0)
        self.assertAlmostEqual(snap["PBR(우선주 포함)"], 100_000 / 1_100.0)
        checks = {c["항목"]: c["판정"] for c in sheet["checks"]}
        self.assertEqual(checks["시가총액(보통주) 검산"], "✅")   # 100원 × 보통주 1,000주 = 네이버 100,000
        self.assertEqual(checks["BPS(보통+우선)"], "✅")
        self.assertFalse(any("어느 쪽과도" in w for w in sheet["warnings"]))  # Yahoo 1,000주 = 보통주 발행
        self.assertIn("| 유통주식수(보통+우선) | 1,100주 |", fs.render(sheet))

    def test_fiscal_year_fallback_when_no_ttm(self):
        sheet = self._korea_with_shares({"005935"}, basis=False)
        snap = sheet["snapshot"]
        self.assertAlmostEqual(snap["EPS(보통+우선 유통주식)"]["value"], 96.0 / 1_100)
        self.assertIn("FY2025", snap["EPS(보통+우선 유통주식)"]["source"])

    def test_multiple_preferred_classes_withhold_market_cap(self):
        sheet = self._korea_with_shares({"005935", "005937"}, yahoo_shares=950.0)
        self.assertNotIn("PER(우선주 포함)", sheet["snapshot"])
        self.assertNotIn("시가총액(보통+우선, 유통주식)", sheet["snapshot"])
        self.assertIsNotNone(sheet["snapshot"]["BPS(보통+우선 유통주식)"]["value"])  # 시세 없이 계산 가능
        self.assertTrue(any("2종류" in w for w in sheet["warnings"]))
        self.assertTrue(any("어느 쪽과도" in w for w in sheet["warnings"]))  # Yahoo 950주

    def test_share_counts_parses_dart_rows(self):
        import dart_data
        row = lambda se, issued, tes, distb, no="R2": {"rcept_no": no, "se": se, "istc_totqy": issued,
                                                         "tesstk_co": tes, "distb_stock_co": distb,
                                                         "stlm_dt": "2026-06-30"}
        self.patch(dart_data, "_acc_month", return_value=12)
        self.patch(dart_data, "periodic_reports_as_of", return_value=[
            ("20260814", "R2", "반기보고서 (2026.06)", "11012", 2026)])
        self.patch(dart_data, "_api_json", return_value={"list": [
            row("보통주", "1,000", "100", "900"), row("우선주", "200", "-", "200"),
            row("보통주", "9,999", "-", "9,999", no="OLD")]})
        sc = dart_data.share_counts("00126380", "2026-10-28")
        self.assertEqual(sc["보통주"], {"발행": 1000.0, "자기주식": 100.0, "유통": 900.0})
        self.assertEqual(sc["우선주"], {"발행": 200.0, "자기주식": 0.0, "유통": 200.0})
        self.assertEqual((sc["기준일"], sc["접수번호"]), ("2026-06-30", "R2"))

    def test_grade_thresholds(self):
        self.assertEqual(fs.grade(100, 100.9)[1], "✅")
        self.assertEqual(fs.grade(100, 104)[1], "⚠️")
        self.assertEqual(fs.grade(100, 110)[1], "❌")
        self.assertEqual(fs.grade(None, 1)[1], "비교 불가")


if __name__ == "__main__":
    unittest.main()
