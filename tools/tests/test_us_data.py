"""미국 데이터 도구 오프라인 테스트 — 네트워크 없이 응답 형식 픽스처로 검증.

실행: python3 -m unittest discover -s tools/tests -v
"""
import contextlib
import io
import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import _us_common  # noqa: E402
import alphavantage_data  # noqa: E402
import fred_data  # noqa: E402
import polymarket_data  # noqa: E402
import sec_edgar_data  # noqa: E402

YESTERDAY = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")


def run_cli(module, argv):
    """모듈 CLI를 run(main)으로 실행 → (종료 코드, 출력)."""
    out = io.StringIO()
    code = 0
    with mock.patch.object(sys, "argv", ["prog"] + argv), contextlib.redirect_stdout(out):
        try:
            _us_common.run(module.main)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue()


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

class CommonTest(unittest.TestCase):
    def test_parse_as_of_normalizes_and_clamps_future(self):
        self.assertEqual(_us_common.parse_as_of("2026-7-3"), "2026-07-03")
        future = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        self.assertEqual(_us_common.parse_as_of(future), _us_common.today())
        self.assertEqual(_us_common.parse_as_of(""), _us_common.today())

    def test_fmt_usd_millions_small_values_not_zero(self):
        self.assertEqual(_us_common.fmt_usd_millions(39_572_000_000), "39,572")
        self.assertEqual(_us_common.fmt_usd_millions(250_000), "0.25")
        self.assertEqual(_us_common.fmt_usd_millions(None), "-")


# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------

def _fact(val, end, filed, form="10-K", start=None):
    f = {"val": val, "end": end, "filed": filed, "form": form}
    if start:
        f["start"] = start
    return f


# 애플 2008 회계연도 총자산: 2008-11 공시 396억 → 2010-01 정정 공시 362억 (원본 TradingAgents 주석 사례)
FACTS = {"facts": {"us-gaap": {
    "Assets": {"units": {"USD": [
        _fact(39_572_000_000, "2008-09-27", "2008-11-05"),
        _fact(36_171_000_000, "2008-09-27", "2010-01-25", form="10-K/A"),
        _fact(47_501_000_000, "2009-09-26", "2009-10-27"),
    ]}},
    "StockholdersEquity": {"units": {"USD": [
        _fact(21_030_000_000, "2008-09-27", "2008-11-05"),
        _fact(31_640_000_000, "2009-09-26", "2009-10-27"),
    ]}},
    "Liabilities": {"units": {"USD": [
        _fact(18_542_000_000, "2008-09-27", "2008-11-05"),
        _fact(15_861_000_000, "2009-09-26", "2009-10-27"),
    ]}},
    # 매출: 연간(10-K) + 10-Q가 보고한 12개월 합계(연간으로 착각하면 안 됨) + 분기
    "Revenues": {"units": {"USD": [
        _fact(32_479_000_000, "2008-09-27", "2008-11-05", start="2007-09-30"),
        _fact(42_905_000_000, "2009-09-26", "2009-10-27", start="2008-09-28"),
        _fact(99_000_000_000, "2009-06-27", "2009-07-22", form="10-Q", start="2008-06-29"),
        _fact(9_734_000_000, "2009-06-27", "2009-07-22", form="10-Q", start="2009-03-29"),
    ]}},
    "NetIncomeLoss": {"units": {"USD": [
        _fact(4_834_000_000, "2008-09-27", "2008-11-05", start="2007-09-30"),
        _fact(8_235_000_000, "2009-09-26", "2009-10-27", start="2008-09-28"),
    ]}},
    "EarningsPerShareDiluted": {"units": {"USD/shares": [
        _fact(5.36, "2008-09-27", "2008-11-05", start="2007-09-30"),
    ]}},
    # 현금흐름: 10-Q가 6개월 누계로만 공시
    "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
        _fact(9_596_000_000, "2008-09-27", "2008-11-05", start="2007-09-30"),
        _fact(10_159_000_000, "2009-09-26", "2009-10-27", start="2008-09-28"),
        _fact(5_100_000_000, "2009-03-28", "2009-04-22", form="10-Q", start="2008-09-28"),
    ]}},
    "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
        _fact(1_091_000_000, "2008-09-27", "2008-11-05", start="2007-09-30"),
        _fact(1_144_000_000, "2009-09-26", "2009-10-27", start="2008-09-28"),
    ]}},
}}}
TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
SUBMISSIONS = {"filings": {"recent": {
    "form": ["10-K", "8-K", "10-Q"],
    "filingDate": ["2009-10-27", "2009-08-01", "2009-07-22"],
    "reportDate": ["2009-09-26", "", "2009-06-27"],
    "accessionNumber": ["0001193125-09-214859", "0001193125-09-100000", "0001193125-09-153165"],
    "primaryDocument": ["d10k.htm", "d8k.htm", "d10q.htm"],
}}}


def fake_sec_get_json(url, params=None, headers=None, secret=""):
    assert headers and "@" in headers["User-Agent"], "SEC는 연락 이메일이 든 User-Agent 필요"
    if "company_tickers" in url:
        return TICKERS
    if "companyfacts" in url:
        return FACTS
    if "submissions" in url:
        return SUBMISSIONS
    raise AssertionError(url)


class SecEdgarTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(sec_edgar_data, "get_json", side_effect=fake_sec_get_json),
            mock.patch.object(sec_edgar_data, "read_cache", return_value=None),
            mock.patch.object(sec_edgar_data, "write_cache"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.us_gaap = FACTS["facts"]["us-gaap"]

    def test_restatement_applies_only_from_its_filing_date(self):
        spans = (sec_edgar_data._SPANS["annual"],)
        before, _ = sec_edgar_data.values_as_of(self.us_gaap, ("Assets",), "2009-12-31", spans)
        after, _ = sec_edgar_data.values_as_of(self.us_gaap, ("Assets",), "2010-06-30", spans)
        self.assertEqual(before[("2008-09-27", 0)], 39_572_000_000)
        self.assertEqual(after[("2008-09-27", 0)], 36_171_000_000)

    def test_facts_filed_after_as_of_are_invisible(self):
        spans = (sec_edgar_data._SPANS["annual"],)
        vals, _ = sec_edgar_data.values_as_of(self.us_gaap, ("Assets",), "2009-01-01", spans)
        self.assertNotIn(("2009-09-26", 0), vals)

    def test_annual_ignores_10q_twelve_month_total(self):
        rows, _, _ = sec_edgar_data.statement_table(self.us_gaap, "income", "annual", "2010-12-31")
        periods = [p for p, _ in rows]
        self.assertNotIn("2009-06-27", periods)
        self.assertEqual(dict(rows)["2009-09-26"]["매출"], 42_905_000_000)

    def test_quarterly_uses_quarter_span_and_labels_year_to_date(self):
        rows, _, _ = sec_edgar_data.statement_table(self.us_gaap, "income", "quarterly", "2010-12-31")
        self.assertEqual(dict(rows)["2009-06-27"]["매출"], 9_734_000_000)
        cf_rows, _, _ = sec_edgar_data.statement_table(self.us_gaap, "cashflow", "quarterly", "2010-12-31")
        self.assertIn("2009-03-28 (6개월 누계)", dict(cf_rows))

    def test_eps_keeps_its_unit(self):
        _, units, _ = sec_edgar_data.statement_table(self.us_gaap, "income", "annual", "2010-12-31")
        self.assertEqual(units["희석EPS"], "USD/shares")

    def test_cli_financials_as_of_and_derived_metrics(self):
        code, out = run_cli(sec_edgar_data, ["financials", "AAPL", "--as-of", "2009-12-31"])
        self.assertEqual(code, 0, out)
        self.assertIn("39,572", out)          # 정정 전 값
        self.assertNotIn("36,171", out)
        self.assertIn("2009-09-26 기준", out)  # 파생 지표는 최신 연간 한 기간 값으로
        self.assertIn("FCF:            9,015", out)  # 10,159 - 1,144
        self.assertIn("이 회사가 태깅하지 않은 계정", out)

    def test_no_filings_before_as_of_is_not_reported_as_untagged(self):
        # 태그는 있는데 as_of 이전 공시가 없는 것과, 회사가 태그를 쓰지 않는 것은 다르다.
        code, out = run_cli(sec_edgar_data, ["financials", "AAPL", "--statement", "balance",
                                             "--as-of", "2000-01-01"])
        self.assertEqual(code, _us_common.EXIT_NO_DATA, out)
        untagged_line = next(ln for ln in out.splitlines() if "태깅하지 않은" in ln)
        self.assertIn("유동자산", untagged_line)  # 픽스처에 태그 자체가 없음
        for label in ("자산총계", "부채총계", "자본총계"):
            self.assertNotIn(label, untagged_line)
        self.assertIn("공시된 연간 데이터 없음", out)

    def test_cli_unknown_ticker_is_no_data(self):
        code, out = run_cli(sec_edgar_data, ["financials", "ZZZZ"])
        self.assertEqual(code, _us_common.EXIT_NO_DATA)
        self.assertTrue(out.startswith("NO_DATA:"))

    def test_cli_filings_respects_as_of_and_forms(self):
        code, out = run_cli(sec_edgar_data, ["filings", "AAPL", "--forms", "10-K,10-Q", "--as-of", "2009-09-01"])
        self.assertEqual(code, 0, out)
        self.assertIn("10-Q", out)
        self.assertNotIn("10-K ", out)
        self.assertNotIn("8-K", out)
        self.assertIn("/Archives/edgar/data/320193/000119312509153165/d10q.htm", out)

    def test_network_failure_is_unavailable(self):
        with mock.patch.object(sec_edgar_data, "get_json",
                               side_effect=_us_common.UnavailableError("HTTP 403")):
            code, out = run_cli(sec_edgar_data, ["resolve", "AAPL"])
        self.assertEqual(code, _us_common.EXIT_UNAVAILABLE)
        self.assertTrue(out.startswith("UNAVAILABLE:"))


# ---------------------------------------------------------------------------
# FRED
# ---------------------------------------------------------------------------

class FredTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"FRED_API_KEY": "SECRETKEY"})
        p.start()
        self.addCleanup(p.stop)
        self.calls = []

    def fake_http_get(self, url, params=None, headers=None, secret="", timeout=30):
        self.calls.append((url, dict(params)))
        if url.endswith("/series"):
            return 200, json.dumps({"seriess": [{"title": "CPI", "units_short": "Index",
                                                 "frequency": "Monthly",
                                                 "seasonal_adjustment_short": "SA"}]})
        return 200, json.dumps({"observations": [
            {"date": "2022-01-01", "value": "281.1"},
            {"date": "2022-02-01", "value": "."},
            {"date": "2022-05-01", "value": "291.5"},
        ]})

    def test_vintage_is_pinned_to_as_of(self):
        with mock.patch.object(fred_data, "http_get", side_effect=self.fake_http_get):
            code, out = run_cli(fred_data, ["series", "cpi", "--as-of", "2022-06-30"])
        self.assertEqual(code, 0, out)
        for _, params in self.calls:
            self.assertEqual(params["realtime_start"], "2022-06-30")
            self.assertEqual(params["realtime_end"], "2022-06-30")
            self.assertEqual(params["series_id"], "CPIAUCSL")
        self.assertIn("최신: 291.5 (2022-05-01)", out)
        self.assertNotIn("| .", out)  # 결측 "." 제외

    def test_missing_key_is_not_configured(self):
        with mock.patch.dict(os.environ, {"FRED_API_KEY": ""}):
            code, out = run_cli(fred_data, ["series", "cpi"])
        self.assertEqual(code, _us_common.EXIT_NOT_CONFIGURED)

    def test_bad_series_is_no_data_and_key_scrubbed(self):
        bad = mock.Mock(return_value=(400, json.dumps(
            {"error_message": "Bad Request. The series does not exist. api_key=SECRETKEY"})))
        with mock.patch.object(fred_data, "http_get", bad):
            code, out = run_cli(fred_data, ["series", "NOTASERIES"])
        self.assertEqual(code, _us_common.EXIT_NO_DATA)
        self.assertNotIn("SECRETKEY", out)

    def test_invalid_key_is_not_configured_not_no_data(self):
        # 실제 FRED 응답(2026-10 확인): 무효 키도 HTTP 400 + error_message
        bad = mock.Mock(return_value=(400, json.dumps({"error_code": 400, "error_message":
            "Bad Request.  The value for variable api_key is not registered.  "
            "Read https://fred.stlouisfed.org/docs/api/api_key.html for more information."})))
        with mock.patch.object(fred_data, "http_get", bad):
            code, out = run_cli(fred_data, ["series", "cpi"])
        self.assertEqual(code, _us_common.EXIT_NOT_CONFIGURED, out)
        self.assertTrue(out.startswith("NOT_CONFIGURED:"))
        self.assertNotIn("SECRETKEY", out)

    def test_phrase_is_rejected_before_request(self):
        with self.assertRaises(_us_common.NoDataError):
            fred_data.resolve_series_id("bank of japan rate")


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------

class PolymarketTest(unittest.TestCase):
    def test_historical_as_of_is_withheld_without_request(self):
        with mock.patch.object(polymarket_data, "get_json") as g:
            code, out = run_cli(polymarket_data, ["search", "Fed rate cut", "--as-of", YESTERDAY])
        self.assertEqual(code, _us_common.EXIT_WITHHELD)
        self.assertTrue(out.startswith("WITHHELD:"))
        g.assert_not_called()

    def test_only_open_future_markets_sorted_by_volume(self):
        future = (date.today() + timedelta(days=60)).isoformat() + "T00:00:00Z"
        data = {"events": [{"markets": [
            {"question": "closed one", "closed": True, "outcomes": '["Yes","No"]',
             "outcomePrices": '["0.9","0.1"]', "volumeNum": 9e9, "endDate": future},
            {"question": "past one", "outcomes": '["Yes","No"]', "outcomePrices": '["0.5","0.5"]',
             "volumeNum": 8e9, "endDate": "2020-01-01T00:00:00Z"},
            {"question": "small", "outcomes": '["Yes","No"]', "outcomePrices": '["0.2","0.8"]',
             "volumeNum": 1000, "endDate": future},
            {"question": "big", "outcomes": '["Yes","No"]', "outcomePrices": '["0.76","0.24"]',
             "volumeNum": 5e6, "endDate": future, "oneWeekPriceChange": 0.05},
        ]}]}
        with mock.patch.object(polymarket_data, "get_json", return_value=data):
            code, out = run_cli(polymarket_data, ["search", "Fed"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("closed one", out)
        self.assertNotIn("past one", out)
        self.assertLess(out.index("big"), out.index("small"))
        self.assertIn("Yes 76%", out)
        self.assertIn("1주 +5.0%p", out)

    def test_odds_near_edges_keep_digits(self):
        self.assertEqual(polymarket_data.fmt_odds(0.0005), "0.05%")
        self.assertEqual(polymarket_data.fmt_odds(0.9995), "99.95%")
        self.assertEqual(polymarket_data.fmt_odds(0.5), "50%")


# ---------------------------------------------------------------------------
# Alpha Vantage
# ---------------------------------------------------------------------------

class AlphaVantageTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "AVKEY"})
        p.start()
        self.addCleanup(p.stop)

    def test_rate_limit_checked_before_key_wording(self):
        with self.assertRaises(_us_common.UnavailableError):
            alphavantage_data.classify_notice(
                {"Information": "Thank you for using Alpha Vantage! Our standard API rate limit is "
                                "25 requests per day. Please subscribe ... your API key"})
        with self.assertRaises(_us_common.NotConfiguredError):
            alphavantage_data.classify_notice({"Information": "the parameter apikey is invalid or missing."})
        with self.assertRaises(_us_common.UnavailableError):
            alphavantage_data.classify_notice({"Error Message": "Invalid API call."})

    def test_statement_and_overview_withheld_for_past_dates(self):
        for argv in (["statement", "NVDA", "--as-of", YESTERDAY],
                     ["overview", "NVDA", "--as-of", YESTERDAY],
                     ["insider", "NVDA", "--as-of", YESTERDAY]):
            with mock.patch.object(alphavantage_data, "http_get") as h:
                code, out = run_cli(alphavantage_data, argv)
            self.assertEqual(code, _us_common.EXIT_WITHHELD, argv)
            h.assert_not_called()

    def test_daily_rows_after_as_of_are_cut(self):
        csv_body = ("timestamp,open,high,low,close,volume\n"
                    "2025-07-02,10,11,9,10.5,1000\n"
                    "2025-06-30,9,10,8,9.5,2000\n"
                    "2025-06-27,8,9,7,8.5,3000\n")
        with mock.patch.object(alphavantage_data, "http_get", return_value=(200, csv_body)):
            code, out = run_cli(alphavantage_data, ["daily", "NVDA", "--days", "10", "--as-of", "2025-06-30"])
        self.assertEqual(code, 0, out)
        self.assertIn("2025-06-30", out)
        self.assertNotIn("2025-07-02", out)

    def test_news_after_as_of_is_cut_even_if_api_returns_it(self):
        payload = {"feed": [
            {"time_published": "20250701T090000", "title": "FUTURE", "source": "x"},
            {"time_published": "20250630T235900", "title": "SAME-DAY", "source": "x"},
            {"time_published": "", "title": "NODATE", "source": "x"},
            {"time_published": "20250629T120000", "title": "PAST", "source": "x"}]}
        with mock.patch.object(alphavantage_data, "http_get", return_value=(200, json.dumps(payload))):
            code, out = run_cli(alphavantage_data, ["news", "NVDA", "--days", "3", "--as-of", "2025-06-30"])
        self.assertEqual(code, 0, out)
        self.assertIn("SAME-DAY", out)
        self.assertIn("PAST", out)
        self.assertNotIn("FUTURE", out)
        self.assertNotIn("NODATE", out)
        self.assertIn("2건", out)

    def test_premium_endpoint_notice_is_unavailable(self):
        notice = {"Information": "Thank you for using Alpha Vantage! This is a premium endpoint. You may "
                                 "subscribe to any of the premium plans at https://www.alphavantage.co/premium/"}
        with mock.patch.object(alphavantage_data, "http_get", return_value=(200, json.dumps(notice))):
            code, out = run_cli(alphavantage_data, ["overview", "NVDA"])
        self.assertEqual(code, _us_common.EXIT_UNAVAILABLE, out)

    def test_statement_formats_current(self):
        payload = {"annualReports": [
            {"fiscalDateEnding": "2025-01-26", "reportedCurrency": "USD", "totalRevenue": "130497000000",
             "grossProfit": "97858000000", "operatingIncome": "81453000000", "netIncome": "72880000000",
             "ebitda": "None", "researchAndDevelopment": "12914000000"}]}
        with mock.patch.object(alphavantage_data, "http_get", return_value=(200, json.dumps(payload))):
            code, out = run_cli(alphavantage_data, ["statement", "NVDA"])
        self.assertEqual(code, 0, out)
        self.assertIn("130,497", out)
        self.assertIn("| -", out)  # "None" → "-"

    def test_unexpected_csv_column_is_error_not_untrimmed(self):
        with self.assertRaises(_us_common.UnavailableError):
            alphavantage_data.filter_csv("date,close\n2025-01-01,1\n", "2024-01-01", "2025-01-01", "timestamp")


if __name__ == "__main__":
    unittest.main()
