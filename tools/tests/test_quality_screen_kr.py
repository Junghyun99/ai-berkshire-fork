"""부실기업 스크리닝(quality_screen_kr) 오프라인 테스트 — DART 응답 대신 합성 계정으로 지표·판정을 검증.

실행: python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import quality_screen_kr as q  # noqa: E402

E = 1e12  # 1조


def item(sj, aid, nm, *vals):
    cols = dict(zip(q.COLS, [f"{v:,.0f}" if v is not None else "" for v in vals]))
    return dict(sj_div=sj, account_id=aid, account_nm=nm, **cols)


def report(rev, gp, op, ni, eq, ocf, capex, interest):
    """3개년(당기·전기·전전기) 값 튜플로 fnlttSinglAcntAll list 흉내."""
    return [
        item("IS", "ifrs-full_Revenue", "매출액", *rev),
        item("IS", "ifrs-full_GrossProfit", "매출총이익", *gp),
        item("IS", "dart_OperatingIncomeLoss", "영업이익", *op),
        item("IS", "ifrs-full_ProfitLoss", "당기순이익", *ni),
        item("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주지분", *ni),
        item("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분", *eq),
        item("BS", "ifrs-full_Equity", "자본총계", *eq),
        item("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", *ocf),
        item("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
             "유형자산의 취득", *capex),
        item("IS", "ifrs-full_InterestExpense", "이자비용", *interest),
    ]


def steady(base=2025, rev=10 * E, gm=0.4, nm=0.1, roe=0.15, ocf_ratio=1.2, capex=0.5 * E, interest=0.05 * E):
    """매년 같은 비율의 우량 기업 보고서 4건(Y, Y-3, Y-6, Y-9)."""
    eq = rev * nm / roe
    reps = []
    for ry in q.report_years(base):
        t = lambda v: (v, v, v)  # noqa: E731
        reps.append((ry, "CFS", "KRW", report(t(rev), t(rev * gm), t(rev * nm * 1.3), t(rev * nm), t(eq),
                                             t(rev * nm * ocf_ratio), t(capex), t(interest))))
    return reps


class ExtractTest(unittest.TestCase):
    def test_account_id_wins_and_negative_parentheses(self):
        items = [item("IS", "x", "매출액", 1, 2, 3), item("IS", "ifrs-full_Revenue", "영업수익", 10, 20, 30),
                 item("IS", "dart_OperatingIncomeLoss", "영업이익", -5, 0, 5)]
        items[2]["thstrm_amount"] = "(5)"
        ex = q.extract(items)
        self.assertEqual(ex["rev"], [10, 20, 30])
        self.assertEqual(ex["op"][0], -5)

    def test_owner_equity_not_matched_by_name(self):
        # 계정명만 같은 줄(예: 자본금이 잘못 태깅된 경우)은 지배지분 자본으로 잡지 않는다
        ex = q.extract([item("BS", "dart_Other", "지배기업의 소유주에게 귀속되는 자본", 1, 1, 1)])
        self.assertNotIn("eq_own", ex)


class MergeTest(unittest.TestCase):
    def test_latest_report_wins_and_gaps_filled(self):
        new = (2025, "CFS", "KRW", [item("IS", "ifrs-full_Revenue", "매출액", 300, 200, 100)])
        old = (2022, "CFS", "KRW", [item("IS", "ifrs-full_Revenue", "매출액", 90, 80, 70)])
        data, basis, _ = q.merge_reports([old, new], multi={2019: ({"rev": 60}, "CFS"), 2023: ({"rev": 1}, "CFS")})
        self.assertEqual(data[2023]["rev"], 100)          # 다중조회가 전체 재무제표를 덮지 않음
        self.assertEqual(data[2020]["rev"], 70)
        self.assertEqual(data[2019]["rev"], 60)
        self.assertEqual(basis[2019], "CFS-주요계정")

    def test_foreign_currency_converted_or_flagged(self):
        rep = (2025, "CFS", "USD", [item("IS", "ifrs-full_Revenue", "매출액", 10, 10, 10)])
        data, basis, missing = q.merge_reports([rep], fx={2025: 1400.0, 2024: 1350.0})
        self.assertEqual(data[2025]["rev"], 14000)
        self.assertEqual(basis[2025], "CFS-USD환산")
        self.assertEqual(missing, [2023])
        self.assertNotIn(2023, data)

    def test_service_company_without_cogs(self):
        rep = (2025, "CFS", "KRW", [item("IS", "ifrs-full_Revenue", "영업수익", 100, 100, 100),
                                    item("IS", "ifrs-full_GrossProfit", "매출총이익", 100, 100, 100)])
        data, _, _ = q.merge_reports([rep])
        self.assertNotIn("gp", data[2025])


class MetricsJudgeTest(unittest.TestCase):
    def metrics(self, **kw):
        data, _, _ = q.merge_reports(steady(**kw))
        return q.compute_metrics(data, 2025, shares_then=100, shares_now=100)

    def test_quality_company_passes(self):
        m = self.metrics()
        self.assertAlmostEqual(m["roe10"], 0.15, places=6)
        self.assertAlmostEqual(m["gm10"], 0.4, places=6)
        self.assertAlmostEqual(m["ocfni5"], 1.2, places=6)
        self.assertAlmostEqual(m["icr"], 26.0, places=6)
        j = q.judge(m)
        self.assertEqual(j["verdict"], "통과")
        self.assertEqual(j["fails"], [])

    def test_each_threshold(self):
        self.assertEqual(q.judge(self.metrics(roe=0.07))["fails"], [1])
        self.assertEqual(q.judge(self.metrics(capex=2 * E))["fails"], [2])
        self.assertEqual(q.judge(self.metrics(interest=0.7 * E))["fails"], [3])
        self.assertEqual(q.judge(self.metrics(gm=0.12))["fails"], [4])
        self.assertEqual(q.judge(self.metrics(ocf_ratio=0.6))["fails"], [5])
        self.assertIn(6, q.judge(self.metrics(nm=0.04, roe=0.15))["fails"])

    def test_borderline_is_warn_not_fail(self):
        j = q.judge(self.metrics(roe=0.085))
        self.assertEqual(j["cells"][1]["s"], "warn")
        self.assertEqual(j["verdict"], "통과")

    def test_dilution(self):
        m = self.metrics()
        m["dilution5"] = 0.5
        self.assertEqual(q.judge(m)["fails"], [7])
        j = q.judge(m, dilution_ok="액면분할 5:1")
        self.assertEqual(j["verdict"], "통과")
        self.assertEqual(j["cells"][7]["note"], "액면분할 5:1")

    def test_exemption_a_requires_young(self):
        m = self.metrics(roe=0.05)
        self.assertEqual(q.judge(m)["verdict"], "배제")
        j = q.judge(m, young=True)
        self.assertEqual((j["verdict"], j["exempt"]), ("면제 통과", ["A"]))

    def test_exemption_b_high_gross_margin_recovering(self):
        data, _, _ = q.merge_reports(steady(nm=0.04, roe=0.12, gm=0.5))
        data[2024]["ni"] = data[2024]["rev"] * 0.06
        data[2025]["ni"] = data[2025]["rev"] * 0.07
        j = q.judge(q.compute_metrics(data, 2025, 100, 100))
        self.assertIn("B", j["exempt"])
        self.assertEqual(j["cells"][6]["s"], "exempt")

    def test_exemption_c_needs_business_model_flag(self):
        m = self.metrics(gm=0.12, nm=0.03, roe=0.25, capex=0.1 * E)
        self.assertEqual(q.judge(m)["verdict"], "배제")
        j = q.judge(m, costco_type=True)
        self.assertEqual((j["verdict"], j["exempt"]), ("면제 통과", ["C"]))

    def test_financial_only_roe_and_dilution(self):
        m = self.metrics(gm=0.0, capex=5 * E, interest=5 * E)
        j = q.judge(m, financial=True)
        self.assertEqual(j["verdict"], "통과")
        self.assertEqual({k for k, c in j["cells"].items() if c["s"] == "skip"}, {2, 3, 4, 5, 6})

    def test_operating_loss_and_cumulative_loss(self):
        data, _, _ = q.merge_reports(steady())
        for y in range(2021, 2026):
            data[y]["ni"] = data[y]["ni_own"] = -1 * E
        data[2025]["op"] = -1 * E
        j = q.judge(q.compute_metrics(data, 2025, 100, 100))
        self.assertEqual(j["cells"][3]["t"], "영업적자")
        self.assertEqual(j["cells"][5]["t"], "누적적자")

    def test_overrides(self):
        m = self.metrics(ocf_ratio=0.5)
        j = q.judge(m, cell_override={"5": ["adj", "1.69", "일회성 처분이익 제외"]})
        self.assertEqual(j["verdict"], "면제 통과")
        j = q.judge(m, verdict_override=["판정 보류", "지분법 구조"])
        self.assertEqual((j["verdict"], j["reason"]), ("판정 보류", "지분법 구조"))

    def test_recent_listing_label(self):
        data, _, _ = q.merge_reports(steady())
        m = q.compute_metrics(data, 2025, shares_then=None, shares_now=100)
        self.assertEqual(q.judge(m)["cells"][7]["t"], "상장 5년 미만")


class MiscTest(unittest.TestCase):
    def test_is_financial(self):
        self.assertTrue(q.is_financial("64121", "기업은행"))
        self.assertTrue(q.is_financial("65110", "삼성생명"))
        self.assertTrue(q.is_financial("64992", "KB금융지주"))
        self.assertFalse(q.is_financial("64992", "LG"))
        self.assertFalse(q.is_financial("66199", "카카오페이"))

    def test_total_shares(self):
        self.assertEqual(q.total_shares([{"se": "보통주", "istc_totqy": "10"}, {"se": "우선주", "istc_totqy": "-"},
                                         {"se": "합계", "istc_totqy": "10"}]), 10)
        self.assertEqual(q.total_shares([{"se": "보통주", "istc_totqy": "7"}, {"se": "우선주", "istc_totqy": "3"}]), 10)

    def test_default_base_year(self):
        self.assertEqual(q.default_base_year(date(2026, 3, 15)), 2024)
        self.assertEqual(q.default_base_year(date(2026, 10, 31)), 2025)


if __name__ == "__main__":
    unittest.main()
