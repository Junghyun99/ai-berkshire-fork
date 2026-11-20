"""미국 부실기업 스크리닝(quality_screen_us) 오프라인 테스트 — SEC companyfacts 대신 합성 사실로 어댑터를 검증.

지표·판정 자체는 quality_screen_kr 테스트가 다룬다. 여기서는 SEC 사실 → 연도별 계정 변환, 분할에 강한 희석 계산,
업종 자동 분류, 미국판 보정(음(-)자본·REIT·EBIT 근사), 구성종목 파싱을 본다.

실행: python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import quality_screen_us as q  # noqa: E402

B = 1e9


def dur(fy, val, accn=None, form="10-K", filed=None, end_md="12-31"):
    return {"start": f"{fy}-01-01", "end": f"{fy}-{end_md}", "val": val, "form": form,
            "filed": filed or f"{fy + 1}-02-15", "accn": accn or f"A{fy}"}


def inst(fy, val, form="10-K", filed=None):
    return {"end": f"{fy}-12-31", "val": val, "form": form, "filed": filed or f"{fy + 1}-02-15", "accn": f"A{fy}"}


def tag(facts, unit="USD"):
    return {"units": {unit: facts}}


def company(years=range(2016, 2026), rev=100 * B, gm=0.5, nm=0.2, eq=80 * B, ocf_ratio=1.2, capex=5 * B,
            interest=1 * B, shares=None, extra=None):
    """매년 같은 비율의 합성 기업. 10-K마다 당해 값만 싣는다(비교 연도는 생략)."""
    ys = list(years)
    g = {
        "Revenues": tag([dur(y, rev) for y in ys]),
        "GrossProfit": tag([dur(y, rev * gm) for y in ys]),
        "OperatingIncomeLoss": tag([dur(y, rev * nm * 1.3) for y in ys]),
        "NetIncomeLoss": tag([dur(y, rev * nm) for y in ys]),
        "StockholdersEquity": tag([inst(y, eq) for y in [ys[0] - 1] + ys]),
        "NetCashProvidedByUsedInOperatingActivities": tag([dur(y, rev * nm * ocf_ratio) for y in ys]),
        "PaymentsToAcquirePropertyPlantAndEquipment": tag([dur(y, capex) for y in ys]),
        "InterestExpense": tag([dur(y, interest) for y in ys]),
    }
    if shares:
        g["WeightedAverageNumberOfDilutedSharesOutstanding"] = {"units": {"shares": shares}}
    g.update(extra or {})
    return g


def flat_shares(ys, n=1e9):
    """10-K마다 당해·전년 두 해를 같은 값으로 공시."""
    return [f for y in ys for f in (dur(y, n, accn=f"A{y}"), dur(y - 1, n, accn=f"A{y}", filed=f"{y + 1}-02-15"))]


INFO = {"ticker": "TST", "name": "Test Co", "sector": "Information Technology", "sub": "Application Software"}
AS_OF = "2026-11-20"


class AnnualDataTest(unittest.TestCase):
    def test_tags_mapped_by_fiscal_year(self):
        d, cur = q.annual_data(company(), AS_OF)
        self.assertEqual(cur, "USD")
        self.assertAlmostEqual(d[2025]["rev"], 100 * B)
        self.assertAlmostEqual(d[2025]["gp"], 50 * B)
        self.assertAlmostEqual(d[2015]["eq_own"], 80 * B)  # 기초 자본(전년 말)

    def test_as_of_hides_later_filings(self):
        d, _ = q.annual_data(company(), "2024-06-30")
        self.assertNotIn(2024, d)
        self.assertIn(2023, d)

    def test_ifrs_filer_used_when_no_us_gaap(self):
        facts = {"facts": {"ifrs-full": {"Revenue": tag([dur(2025, 10 * B, form="20-F")], "EUR")},
                           "us-gaap": {}}}
        d, cur = q.annual_data(q.merged_facts(facts), AS_OF)
        self.assertEqual(cur, "EUR")
        self.assertAlmostEqual(d[2025]["rev"], 10 * B)

    def test_quarterly_filings_ignored(self):
        quarter = {"start": "2025-10-01", "end": "2025-12-31", "val": 1 * B, "form": "10-Q",
                   "filed": "2026-03-01", "accn": "Q"}
        g = company(extra={"Revenues": tag([dur(2025, 100 * B), quarter])})
        d, _ = q.annual_data(g, AS_OF)
        self.assertAlmostEqual(d[2025]["rev"], 100 * B)


class ShareGrowthTest(unittest.TestCase):
    def test_split_does_not_count_as_dilution(self):
        # 2023년 10:1 분할. 2023 10-K는 2022를 분할 후 기준(10억주)으로 다시 적는다 — 보고서 내부 비율은 1.0
        ys = range(2020, 2026)
        facts = []
        for y in ys:
            now = 1e9 if y >= 2023 else 1e8
            prev = 1e9 if y >= 2023 else 1e8
            facts += [dur(y, now, accn=f"A{y}"), dur(y - 1, prev, accn=f"A{y}")]
        growth, n = q.share_growth({"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": facts}}},
                                   AS_OF)
        self.assertAlmostEqual(growth, 0.0)
        self.assertEqual(n, 5)

    def test_real_dilution_compounds(self):
        facts = []
        for y in range(2020, 2026):
            facts += [dur(y, 1.1 ** (y - 2019), accn=f"A{y}"), dur(y - 1, 1.1 ** (y - 2020), accn=f"A{y}")]
        growth, _ = q.share_growth({"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": facts}}},
                                   AS_OF)
        self.assertAlmostEqual(growth, 1.1 ** 5 - 1)

    def test_too_short_history(self):
        facts = [dur(2025, 1e9, accn="A"), dur(2024, 1e9, accn="A")]
        self.assertEqual(q.share_growth({"WeightedAverageNumberOfDilutedSharesOutstanding":
                                         {"units": {"shares": facts}}}, AS_OF), (None, 0))


class EvaluateTest(unittest.TestCase):
    def ev(self, g, info=INFO, ov=None, as_of=AS_OF):
        return q.evaluate("TST", g, as_of, info, ov or {})

    def test_quality_company_passes(self):
        j = self.ev(company(shares=flat_shares(range(2019, 2026))))
        self.assertEqual(j["verdict"], "통과", j["cells"])
        self.assertEqual(j["fiscal_year"], 2025)
        self.assertEqual(j["cells"][2]["t"], "+95.0B")  # 5년 × (영업CF 24B − 설비투자 5B), 달러 표기(조 아님)

    def test_negative_equity_buyback_company_not_held(self):
        g = company(eq=-5 * B, shares=flat_shares(range(2019, 2026)))
        j = self.ev(g)
        self.assertEqual(j["cells"][1]["s"], "warn")
        self.assertEqual(j["cells"][1]["t"], "음(-)자본")
        self.assertEqual(j["verdict"], "통과")

    def test_reit_roe_skipped(self):
        g = company(nm=0.03, eq=500 * B, shares=flat_shares(range(2019, 2026)))
        j = self.ev(g, info=dict(INFO, sub="Retail REITs"))
        self.assertEqual(j["cells"][1]["s"], "skip")
        self.assertTrue(j["reit"])

    def test_bank_classified_financial(self):
        j = self.ev(company(gm=0.0, shares=flat_shares(range(2019, 2026))), info=dict(INFO, sub="Diversified Banks"))
        self.assertTrue(j["financial"])
        self.assertEqual(j["cells"][3]["s"], "skip")

    def test_ebit_from_pretax_when_operating_income_missing(self):
        g = company(shares=flat_shares(range(2019, 2026)))
        del g["OperatingIncomeLoss"], g["InterestExpense"]
        g["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"] = \
            tag([dur(y, 1 * B) for y in range(2016, 2026)])
        g["InterestPaidNet"] = tag([dur(y, 1 * B) for y in range(2016, 2026)])
        j = self.ev(g)
        self.assertEqual(j["cells"][3]["t"], "2.0배")  # (세전 1 + 이자 1) / 이자 1

    def test_profitloss_only_fills_parent_net_income(self):
        g = company(shares=flat_shares(range(2019, 2026)))
        g["ProfitLoss"] = g.pop("NetIncomeLoss")
        self.assertNotEqual(self.ev(g)["cells"][1]["s"], "na")

    def test_young_listing_auto_and_not_young_override(self):
        g = company(years=range(2019, 2026), nm=0.02, eq=200 * B, shares=flat_shares(range(2019, 2026)))
        self.assertTrue(self.ev(g)["young"])
        self.assertFalse(self.ev(g, ov={"not_young": {"TST": "재상장"}})["young"])

    def test_dilution_flag_and_override(self):
        facts = []
        for y in range(2020, 2026):
            facts += [dur(y, 1.2 ** (y - 2019), accn=f"A{y}"), dur(y - 1, 1.2 ** (y - 2020), accn=f"A{y}")]
        g = company(shares=facts)
        j = self.ev(g)
        self.assertEqual(j["verdict"], "배제")
        self.assertIn("⑦ M&A·상장 효과 확인 필요", j["flags"])
        j = self.ev(g, ov={"dilution_ok": {"TST": "주식 대가 인수"}})
        self.assertEqual(j["verdict"], "통과")

    def test_costco_candidate_flagged_not_exempted(self):
        g = company(gm=0.12, nm=0.025, eq=10 * B, capex=1 * B, shares=flat_shares(range(2019, 2026)))
        info = dict(INFO, sub="Consumer Staples Merchandise Retail")
        j = self.ev(g, info=info)
        self.assertEqual(j["verdict"], "배제")
        self.assertTrue(any(f.startswith("면제 C") for f in j["flags"]))
        self.assertEqual(self.ev(g, info=info, ov={"costco_type": ["TST"]})["verdict"], "면제 통과")

    def test_stale_or_missing_data_raises(self):
        with self.assertRaises(q.NoDataError):
            self.ev(company(years=range(2010, 2016)))
        with self.assertRaises(q.NoDataError):
            self.ev({})


class ConstituentsTest(unittest.TestCase):
    PAGE = """<table class="wikitable"><tr><th>Category</th></tr><tr><td>x</td></tr></table>
    <table class="wikitable sortable" id="whatever"><tbody>
    <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>
    <tr><td><a>MMM</a></td><td>3M</td><td>Industrials</td><td>Industrial Conglomerates</td></tr>
    <tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td></tr>
    </tbody></table>"""

    def test_picks_table_with_ticker_and_sector(self):
        rows = q.parse_constituents(self.PAGE)
        self.assertEqual([r["ticker"] for r in rows], ["MMM", "BRK.B"])
        self.assertEqual(rows[1]["sub"], "Multi-Sector Holdings")

    def test_no_table_is_unavailable(self):
        with self.assertRaises(q.UnavailableError):
            q.parse_constituents("<table class='wikitable'><tr><th>Year</th></tr></table>")

    def test_universe_file_formats(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "u.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"constituents": [{"ticker": "aapl", "name": "Apple", "sector": "IT", "sub": "Hardware"},
                                            "msft"]}, f)
            orig = q.fetch_index
            q.fetch_index = lambda index: [{"ticker": "MSFT", "name": "Microsoft", "sector": "IT", "sub": "Software"}]
            try:
                rows = q.load_universe(p)
            finally:
                q.fetch_index = orig
        self.assertEqual(rows[0], {"ticker": "AAPL", "name": "Apple", "sector": "IT", "sub": "Hardware"})
        self.assertEqual(rows[1]["sub"], "Software")

    def test_overrides_comment_keys_ignored(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"_note": "x", "costco_type": ["COST"]}, f)
            self.assertEqual(q.load_overrides(p), {"costco_type": ["COST"]})


if __name__ == "__main__":
    unittest.main()
