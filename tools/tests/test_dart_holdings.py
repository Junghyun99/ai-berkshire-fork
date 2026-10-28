"""DART 내부자(임원·주요주주)·대량보유 오프라인 테스트 — elestock/majorstock 응답을 픽스처로 대체.

실행: python3 -m unittest discover -s tools/tests -v
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import _us_common  # noqa: E402
import dart_data  # noqa: E402


def ele(dt, name, delta, held, reg="비등기임원", pos="부사장", major="-", no=None):
    return {"rcept_no": no or dt.replace("-", "") + "000001", "rcept_dt": dt, "repror": name,
            "isu_exctv_rgist_at": reg, "isu_exctv_ofcps": pos, "isu_main_shrholdr": major,
            "sp_stock_lmp_cnt": f"{held:,}", "sp_stock_lmp_irds_cnt": delta}


ELESTOCK = [
    ele("2025-01-10", "갑", "1,000", 5_000),
    ele("2026-08-01", "을", "-2,500", 10_000),
    ele("2026-09-01", "병", "300", 800, reg="등기임원", pos="사외이사"),
    ele("2026-10-01", "회장", "7,000,000", 100_000_000, pos="회장", major="사실상지배주주"),
    ele("2026-10-10", "을", "-500", 9_500),
    ele("2026-10-20", "정", "-", 1_000),            # 증감 '-' → 0
    ele("2026-11-01", "미래", "9,999", 9_999),       # as_of 이후 → 제외
]

MAJOR = [
    {"rcept_no": "20240101000001", "rcept_dt": "2024-01-01", "repror": "A사", "stkqy": "1,000", "stkqy_irds": "1,000",
     "stkrt": "7.00", "stkrt_irds": "7.00", "report_tp": "일반", "report_resn": "- 신규 보고"},
    {"rcept_no": "20260601000001", "rcept_dt": "2026-06-01", "repror": "A사", "stkqy": "900", "stkqy_irds": "-100",
     "stkrt": "6.30", "stkrt_irds": "-0.70", "report_tp": "일반", "report_resn": "- 보유주식수 변동\n- 장내매도"},
    {"rcept_no": "20260701000001", "rcept_dt": "2026-07-01", "repror": "B운용", "stkqy": "2,000", "stkqy_irds": "2,000",
     "stkrt": "12.00", "stkrt_irds": "12.00", "report_tp": "약식", "report_resn": "- 신규"},
    {"rcept_no": "20261105000001", "rcept_dt": "2026-11-05", "repror": "A사", "stkqy": "0", "stkqy_irds": "-900",
     "stkrt": "0.00", "stkrt_irds": "-6.30", "report_tp": "일반", "report_resn": "- 전량 매도"},
]


class HoldingsSummaryTest(unittest.TestCase):
    def test_insiders_window_and_aggregation(self):
        s = dart_data.summarize_insiders(ELESTOCK, "2026-10-28", 180)
        self.assertEqual([r["repror"] for r in s["rows"]], ["을", "병", "회장", "을", "정"])  # 2025·미래 제외
        self.assertEqual((s["증가건"], s["증가주식"]), (2, 7_000_300))
        self.assertEqual((s["감소건"], s["감소주식"]), (2, -3_000))
        eul = [p for p in s["people"] if p["이름"] == "을"][0]
        self.assertEqual((eul["보고"], eul["순증감"], eul["보유"], eul["최근접수"]), (2, -3_000, 9_500, "2026-10-10"))
        self.assertEqual(s["people"][0]["이름"], "회장")              # |순증감| 큰 순

    def test_major_latest_holding_as_of(self):
        s = dart_data.summarize_major(MAJOR, "2026-10-28", 365)
        self.assertEqual([(r["repror"], r["stkrt"]) for r in s["holders"]], [("B운용", "12.00"), ("A사", "6.30")])
        self.assertEqual([r["rcept_dt"] for r in s["changes"]], ["2026-06-01", "2026-07-01"])
        later = dart_data.summarize_major(MAJOR, "2026-11-30", 365)   # 전량 매도 보고 이후
        self.assertIn(("A사", "0.00"), [(r["repror"], r["stkrt"]) for r in later["holders"]])
        past = dart_data.summarize_major(MAJOR, "2025-01-01", 365)
        self.assertEqual([r["repror"] for r in past["holders"]], ["A사"])


class HoldingsCliTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(dart_data, "_resolve", return_value=("00126380", "삼성전자"))
        p.start()
        self.addCleanup(p.stop)
        self.calls = []

        def fake(endpoint, params, timeout=dart_data._TIMEOUT):
            self.calls.append((endpoint, timeout))
            return {"status": "000", "list": ELESTOCK if endpoint == "elestock.json" else MAJOR}
        p = mock.patch.object(dart_data, "_api_json", side_effect=fake)
        p.start()
        self.addCleanup(p.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(_us_common, "CACHE_DIR", tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def run_cmd(self, fn, *args):
        out, code = io.StringIO(), 0
        with contextlib.redirect_stdout(out):
            try:
                fn(*args)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_insiders_output_and_cache(self):
        code, out = self.run_cmd(dart_data.cmd_insiders, "005930", 180, "2026-10-28", 10)
        self.assertEqual(code, 0, out)
        self.assertIn("보고 5건 · 보고자 4명", out)
        self.assertIn("회장 (비등기임원/회장/사실상지배주주) 순증감 +7,000,000주", out)
        self.assertIn("병 (등기임원/사외이사)", out)
        self.assertIn("주식보상", out)                                 # 증감 사유 경고
        self.assertNotIn("미래", out)
        self.assertEqual(self.calls, [("elestock.json", dart_data._TIMEOUT_BULK)])
        self.run_cmd(dart_data.cmd_insiders, "005930", 30, "2026-10-28", 10)
        self.assertEqual(len(self.calls), 1)                          # 두 번째는 캐시

    def test_insiders_no_reports_in_window_is_no_data(self):
        code, out = self.run_cmd(dart_data.cmd_insiders, "005930", 30, "2025-12-31", 10)
        self.assertEqual(code, 3)
        self.assertIn("NO_DATA", out)

    def test_major_holders_output(self):
        code, out = self.run_cmd(dart_data.cmd_major_holders, "005930", 365, "2026-10-28")
        self.assertEqual(code, 0, out)
        self.assertIn("B운용: 12.00%", out)
        self.assertIn("A사 -100주 → 6.30% (-0.70%p) · 보유주식수 변동 / 장내매도", out)
        self.assertNotIn("전량 매도", out)
        code, out = self.run_cmd(dart_data.cmd_major_holders, "005930", 365, "2026-11-30")
        self.assertIn("A사: 0.00% (0주) · 최근 2026-11-05 일반 — 5% 미만으로 내려간 보고", out)
        code, out = self.run_cmd(dart_data.cmd_major_holders, "005930", 365, "2023-12-31")
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
