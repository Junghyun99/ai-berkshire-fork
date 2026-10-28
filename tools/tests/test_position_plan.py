"""실행 계획 기준선 오프라인 테스트.

실행: python3 -m unittest discover -s tools/tests -v
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import _us_common  # noqa: E402
import position_plan as pp  # noqa: E402

RANGES = {"52주최저": 349.20, "3년최저": 331.83, "3년최저일": "2023-10-30"}


def run_cli(argv):
    out, code = io.StringIO(), 0
    with mock.patch.object(sys, "argv", ["prog"] + argv), contextlib.redirect_stdout(out):
        try:
            _us_common.run(pp.main)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                out.write(e.code)
    return code, out.getvalue()


class BuildPlanTest(unittest.TestCase):
    def test_buy_baseline_tranches_and_state(self):
        p = pp.build_plan("매수", 4, 180000, 220000, price=165000, current_weight=1)
        self.assertEqual(p["비중상한"], 7.5)                       # 10% × 0.75
        self.assertEqual([(t["가격"], t["비중"]) for t in p["분할매수"]],
                         [(170000.0, 2.25), (150000.0, 2.25), (130000.0, 3.0)])
        self.assertEqual(p["현재안전마진"], 17.5)
        self.assertIn("1차까지 실행 가능", p["현재상태"])
        self.assertEqual(p["분할매수"][0]["현재가대비"], 3.0)       # 170,000 / 165,000 − 1

    def test_stop_and_trim_lines_replace_single_trim_price(self):
        # MSFT 2026-10-28: 내재가치 상단 444 → 금지선 510.60(+15%), 추가 축소 577.20(+30%)
        p = pp.build_plan("관망", 3, 420, 444, price=531.33, currency="USD")
        self.assertEqual(p["신규매수금지가"], 510.6)
        self.assertEqual([(x["가격"], x["규모"]) for x in p["축소"]], [(510.6, "1/3"), (577.2, "추가")])
        self.assertIn("현재가가 신규 매수 금지 구간", p["현재상태"])
        self.assertTrue(any("신규 매수 금지선 510.60 USD 이상" in w for w in p["경고"]))
        self.assertTrue(any("보유 시에만 적용" in w for w in p["경고"]))   # 보유 비중 미제공
        line = pp.plan_line(p)
        self.assertIn("510.60 USD 이상 신규 매수 금지, 보유 시 510.60 USD 이상 1/3·577.20 USD 이상 추가 축소", line)

    def test_tranche_reach_against_price_ranges(self):
        p = pp.build_plan("관망", 3, 420, 444, price=531.33, currency="USD", ranges=RANGES)
        self.assertEqual([t["위치"] for t in p["분할매수"]],
                         ["52주 범위 안", "3년 최저 아래(관측 범위 밖)", "3년 최저 아래(관측 범위 밖)"])
        self.assertEqual(p["분할매수"][1]["현재가대비"], -39.0)
        self.assertFalse(any("모든 차수" in w for w in p["경고"]))      # 1차는 52주 범위 안
        deep = pp.build_plan("관망", 3, 300, 340, price=531.33, currency="USD", ranges=RANGES)
        self.assertTrue(any("모든 차수가 52주 최저" in w for w in deep["경고"]))
        none = pp.build_plan("관망", 3, 420, 444, price=531.33, currency="USD")
        self.assertTrue(any("--ticker 필요" in w for w in none["경고"]))
        self.assertIn("미확인", pp.render(none))

    def test_hold_never_executes_and_avoid_is_zero(self):
        hold = pp.build_plan("관망", 3, 180000, 220000, price=120000)
        self.assertIn("대기(관망", hold["현재상태"])
        self.assertEqual(hold["비중상한"], 5.0)
        avoid = pp.build_plan("회피", 5, 180000, 220000, price=120000)
        self.assertEqual((avoid["비중상한"], avoid["분할매수"]), (0.0, []))
        self.assertIn("**분할 매수**: -", pp.plan_line(avoid))

    def test_current_weight_and_usd_rounding(self):
        p = pp.build_plan("매수", 2, 150.0, 190.0, price=230.0, currency="USD", current_weight=4)
        self.assertEqual([t["가격"] for t in p["분할매수"]], [144.5, 127.5, 110.5])
        self.assertIn("신규 매수 금지 구간", p["현재상태"])            # 230 ≥ 190 × 1.15 = 218.5
        self.assertIn("초과분 1.5%p", p["보유조정"])
        self.assertFalse(any("보유 시에만 적용" in w for w in p["경고"]))

    def test_invalid_inputs(self):
        with self.assertRaises(_us_common.NoDataError):
            pp.build_plan("매수", 3, 0, 0)                          # 내재가치 없이 가격대를 만들지 않음
        with self.assertRaises(SystemExit):
            pp.build_plan("매수", 3, 100, 120, split=(50, 40))     # 개수 불일치
        with self.assertRaises(SystemExit):
            pp.build_plan("매수", 3, 100, 120, mos=(10, 20), split=(50, 40))  # 합계 100 아님
        with self.assertRaises(SystemExit):
            pp.build_plan("매수", 3, 100, 120, stop_premium=30, trim_premium=20)  # 추가 축소선이 금지선 아래


class ParsePlanTest(unittest.TestCase):
    def test_round_trip_and_code_block_ignored(self):
        line = pp.plan_line(pp.build_plan("매수", 4, 180000, 220000, price=165000))
        text = f"```\n**실행 계획**: 비중 상한 99% | **분할 매수**: 1원 99%\n```\n\n{line}\n"
        got = pp.parse_plan(text)
        self.assertEqual(got["비중상한"], 7.5)
        self.assertEqual([(t["가격"], t["비중"], t["조건"]) for t in got["분할매수"]],
                         [(170000.0, 2.25, ""), (150000.0, 2.25, ""), (130000.0, 3.0, "")])
        self.assertIn("253,000원 이상 신규 매수 금지", got["축소검토"])

    def test_conditions_are_kept(self):
        # MSFT 최종보고서의 실제 결정 줄
        text = ("**실행 계획**: 비중 상한 5% | **분할 매수**: 377 USD 1.5%(1.0%, FY27 확인 신호 충족 시 +0.5%) / "
                "345 USD 1.5% / 300 USD 2%(반증 조건 미발생 시에만) | **축소 검토**: 511 USD 이상 신규 매수 금지 | "
                "**현재 상태**: 대기")
        got = pp.parse_plan(text)
        self.assertEqual(got["분할매수"], [
            {"가격": 377.0, "비중": 1.5, "조건": "1.0%, FY27 확인 신호 충족 시 +0.5%"},
            {"가격": 345.0, "비중": 1.5, "조건": ""},
            {"가격": 300.0, "비중": 2.0, "조건": "반증 조건 미발생 시에만"}])

    def test_refuses_conflicting_or_bad_lines(self):
        a = "**실행 계획**: 비중 상한 5% | **분할 매수**: 100원 2% / 90원 3%"
        b = "**실행 계획**: 비중 상한 4% | **분할 매수**: 100원 2% / 90원 2%"
        for text, msg in ((a + "\n" + b, "여러 번"), ("본문", "찾지 못했습니다"),
                          ("**실행 계획**: 비중 상한 5% | **분할 매수**: 100원 / 90원 3%", "읽을 수 없습니다"),
                          ("**실행 계획**: 비중 상한 5% | **분할 매수**: 100원 4% / 90원 3%", "넘습니다")):
            with self.assertRaises(_us_common.NoDataError) as cm:
                pp.parse_plan(text)
            self.assertIn(msg, str(cm.exception))


class CliTest(unittest.TestCase):
    def test_from_report_with_ticker_price_ranges_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("**판단**: 관망 | **확신도**: ★★★ | **내재가치**: 193,000~214,000원 | **반증 조건**: x\n")
            with mock.patch.object(pp.dl, "resolve_symbol", return_value=("005930.KS", "KRW", 222000.0)), \
                    mock.patch.object(pp, "fetch_ranges", return_value={"52주최저": 94500.0, "3년최저": 49900.0,
                                                                        "3년최저일": "2024-11-14"}):
                code, out = run_cli(["--from-report", path, "--ticker", "005930", "--json"])
            self.assertEqual(code, 0, out)
            data = json.loads(out)
            self.assertEqual((data["비중상한"], data["분할매수"][0]["가격"]), (5.0, 173000.0))
            self.assertEqual(data["현재안전마진"], -9.1)
            self.assertEqual(data["분할매수"][0]["위치"], "52주 범위 안")
            self.assertEqual(data["신규매수금지가"], 246100.0)            # 214,000 × 1.15
            # 인자가 리포트와 다르면 거부
            code, out = run_cli(["--from-report", path, "--verdict", "매수", "--price", "1"])
            self.assertNotEqual(code, 0)

    def test_price_override_keeps_report_basis(self):
        with mock.patch.object(pp.dl, "resolve_symbol", return_value=("MSFT", "USD", 560.0)), \
                mock.patch.object(pp, "fetch_ranges", return_value=RANGES):
            code, out = run_cli(["--verdict", "관망", "--conviction", "3", "--iv-low", "420", "--iv-high", "444",
                                 "--ticker", "MSFT", "--price", "531.33", "--json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["현재가"], 531.33)

    def test_price_lookup_failure_is_unavailable(self):
        with mock.patch.object(pp.dl, "resolve_symbol", side_effect=ConnectionError("down")):
            code, _ = run_cli(["--verdict", "매수", "--conviction", "3", "--iv-low", "100", "--iv-high", "120",
                               "--ticker", "AAPL"])
        self.assertEqual(code, 4)


class FetchRangesTest(unittest.TestCase):
    def test_lowest_low_and_date(self):
        day = 86400
        fake = {"chart": {"result": [{
            "meta": {"fiftyTwoWeekLow": 349.2, "gmtoffset": -14400},
            "timestamp": [1_700_000_000, 1_700_000_000 + day, 1_700_000_000 + 2 * day],
            "indicators": {"quote": [{"low": [400.0, None, 331.83]}]}}]}}
        with mock.patch("global_stock_data._get_json", return_value=fake):
            r = pp.fetch_ranges("MSFT")
        self.assertEqual((r["52주최저"], r["3년최저"]), (349.2, 331.83))
        self.assertEqual(r["3년최저일"], "2023-11-16")


if __name__ == "__main__":
    unittest.main()
