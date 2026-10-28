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
        p = pp.build_plan("매수", 4, 180000, 220000, price=165000)
        self.assertEqual(p["비중상한"], 7.5)                       # 10% × 0.75
        self.assertEqual([(t["가격"], t["비중"]) for t in p["분할매수"]],
                         [(170000.0, 2.25), (150000.0, 2.25), (130000.0, 3.0)])
        self.assertEqual(p["축소검토가"], 264000.0)                 # 220,000 × 1.2
        self.assertEqual(p["현재안전마진"], 17.5)
        self.assertIn("1차까지 실행 가능", p["현재상태"])

    def test_hold_never_executes_and_avoid_is_zero(self):
        hold = pp.build_plan("관망", 3, 180000, 220000, price=120000)
        self.assertIn("대기(관망", hold["현재상태"])
        self.assertEqual(hold["비중상한"], 5.0)
        avoid = pp.build_plan("회피", 5, 180000, 220000, price=120000)
        self.assertEqual((avoid["비중상한"], avoid["분할매수"]), (0.0, []))
        self.assertIn("**분할 매수**: -", pp.plan_line(avoid))

    def test_current_weight_and_trim_and_usd_rounding(self):
        p = pp.build_plan("매수", 2, 150.0, 190.0, price=230.0, currency="USD", current_weight=4)
        self.assertEqual([t["가격"] for t in p["분할매수"]], [144.5, 127.5, 110.5])
        self.assertIn("축소 검토가 이상", p["현재상태"])
        self.assertIn("초과분 1.5%p", p["보유조정"])

    def test_invalid_inputs(self):
        with self.assertRaises(_us_common.NoDataError):
            pp.build_plan("매수", 3, 0, 0)                          # 내재가치 없이 가격대를 만들지 않음
        with self.assertRaises(SystemExit):
            pp.build_plan("매수", 3, 100, 120, split=(50, 40))     # 개수 불일치
        with self.assertRaises(SystemExit):
            pp.build_plan("매수", 3, 100, 120, mos=(10, 20), split=(50, 40))  # 합계 100 아님


class ParsePlanTest(unittest.TestCase):
    def test_round_trip_and_code_block_ignored(self):
        line = pp.plan_line(pp.build_plan("매수", 4, 180000, 220000, price=165000))
        text = f"```\n**실행 계획**: 비중 상한 99% | **분할 매수**: 1원 99%\n```\n\n{line}\n"
        got = pp.parse_plan(text)
        self.assertEqual(got["비중상한"], 7.5)
        self.assertEqual(got["분할매수"], [(170000.0, 2.25), (150000.0, 2.25), (130000.0, 3.0)])
        self.assertIn("264,000원", got["축소검토"])

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
    def test_from_report_with_ticker_price_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("**판단**: 관망 | **확신도**: ★★★ | **내재가치**: 193,000~214,000원 | **반증 조건**: x\n")
            with mock.patch.object(pp.dl, "resolve_symbol", return_value=("005930.KS", "KRW", 222000.0)):
                code, out = run_cli(["--from-report", path, "--ticker", "005930", "--json"])
            self.assertEqual(code, 0, out)
            data = json.loads(out)
            self.assertEqual((data["비중상한"], data["분할매수"][0]["가격"]), (5.0, 173000.0))
            self.assertEqual(data["현재안전마진"], -9.1)
            # 인자가 리포트와 다르면 거부
            code, out = run_cli(["--from-report", path, "--verdict", "매수", "--price", "1"])
            self.assertNotEqual(code, 0)

    def test_price_lookup_failure_is_unavailable(self):
        with mock.patch.object(pp.dl, "resolve_symbol", side_effect=ConnectionError("down")):
            code, _ = run_cli(["--verdict", "매수", "--conviction", "3", "--iv-low", "100", "--iv-high", "120",
                               "--ticker", "AAPL"])
        self.assertEqual(code, 4)


if __name__ == "__main__":
    unittest.main()
