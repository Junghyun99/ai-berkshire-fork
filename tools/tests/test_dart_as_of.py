"""DART --as-of 시점 통제 오프라인 테스트 — DART API 응답을 픽스처로 대체.

실행: python3 -m unittest discover -s tools/tests -v
"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import dart_data  # noqa: E402

# 정기공시 목록: 2024 사업보고서는 2025-03-11 접수, 2023 사업보고서는 2024-03-12 접수 후 2024-05-20 정정.
LIST = [
    {"rcept_dt": "20250311", "rcept_no": "20250311000001", "report_nm": "사업보고서 (2024.12)"},
    {"rcept_dt": "20241114", "rcept_no": "20241114000002", "report_nm": "분기보고서 (2024.09)"},
    {"rcept_dt": "20240520", "rcept_no": "20240520000003", "report_nm": "[기재정정]사업보고서 (2023.12)"},
    {"rcept_dt": "20240312", "rcept_no": "20240312000004", "report_nm": "사업보고서 (2023.12)"},
    {"rcept_dt": "20240301", "rcept_no": "20240301000005", "report_nm": "주요사항보고서(자기주식취득결정)"},
]


def items(rcept_no, revenue="300,000,000,000,000"):
    return [{"rcept_no": rcept_no, "sj_div": "IS", "account_nm": "매출액", "account_id": "",
             "thstrm_amount": revenue, "frmtrm_amount": "280,000,000,000,000", "bfefrmtrm_amount": "-"}]


class DartAsOfTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.financials = {}  # (연도, 보고서코드, 재무구분) → 응답 항목
        for target, value in ((dart_data, "_resolve"),):
            p = mock.patch.object(target, value, return_value=("00126380", "삼성전자"))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(dart_data, "_api_json", side_effect=self.fake_api)
        p.start()
        self.addCleanup(p.stop)

    def fake_api(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint == "company.json":
            return {"status": "000", "acc_mt": "12"}
        if endpoint == "list.json":
            end = params.get("end_de", "99999999")
            rows = [d for d in LIST if d["rcept_dt"] <= end]
            return {"status": "000", "list": rows, "total_page": 1}
        if endpoint == "fnlttSinglAcntAll.json":
            key = (params["bsns_year"], params["reprt_code"], params["fs_div"])
            got = self.financials.get(key)
            return {"status": "000", "list": got} if got else {"status": "013"}
        raise AssertionError(endpoint)

    def run_cli(self, argv):
        out = io.StringIO()
        code = 0
        with mock.patch.object(sys, "argv", ["dart_data.py"] + argv), contextlib.redirect_stdout(out):
            try:
                dart_data.main()
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def test_report_code_parsing(self):
        self.assertEqual(dart_data.report_code_of("[기재정정]사업보고서 (2023.12)", 12), ("11011", 2023, 12))
        self.assertEqual(dart_data.report_code_of("분기보고서 (2024.03)", 12)[0], "11013")
        self.assertEqual(dart_data.report_code_of("분기보고서 (2024.09)", 12)[0], "11014")
        self.assertEqual(dart_data.report_code_of("반기보고서 (2024.06)", 12)[0], "11012")
        # 3월 결산: 6월 분기 = 1분기, 12월 분기 = 3분기
        self.assertEqual(dart_data.report_code_of("분기보고서 (2024.06)", 3)[0], "11013")
        self.assertEqual(dart_data.report_code_of("분기보고서 (2024.12)", 3)[0], "11014")
        self.assertIsNone(dart_data.report_code_of("주요사항보고서(자기주식취득결정)", 12))

    def test_as_of_before_annual_filing_uses_previous_year(self):
        # 2025-03-01: 2024 사업보고서(2025-03-11 접수)는 아직 공개 전 → 2023 사업보고서
        self.financials[("2023", "11011", "CFS")] = items("20240312000004")
        code, out = self.run_cli(["financials", "005930", "--as-of", "2025-03-01"])
        self.assertEqual(code, 0, out)
        self.assertIn("2023년 사업보고서", out)
        self.assertIn("2025-03-01 까지 접수된 공시 기준", out)
        listing = [p for e, p in self.calls if e == "list.json"][0]
        self.assertEqual((listing["end_de"], listing["last_reprt_at"], listing["pblntf_ty"]), ("20250301", "N", "A"))

    def test_restatement_filed_after_as_of_is_withheld(self):
        # 2024-04-01 시점엔 2023 원공시만 있었는데, API는 2024-05-20 정정 값을 돌려줌 → 보류
        self.financials[("2023", "11011", "CFS")] = items("20240520000003")
        code, out = self.run_cli(["financials", "005930", "--as-of", "2024-04-01"])
        self.assertEqual(code, 5)
        self.assertTrue(out.startswith("WITHHELD:"))
        self.assertIn("rcpNo=20240312000004", out)  # 원공시 링크 안내
        self.assertNotIn("300,000", out)

    def test_restatement_filed_before_as_of_is_served(self):
        self.financials[("2023", "11011", "CFS")] = items("20240520000003")
        code, out = self.run_cli(["financials", "005930", "--as-of", "2024-06-30"])
        self.assertEqual(code, 0, out)
        self.assertIn("[기재정정]사업보고서 (2023.12)", out)

    def test_consolidated_missing_falls_back_to_separate(self):
        self.financials[("2023", "11011", "OFS")] = items("20240312000004")
        code, out = self.run_cli(["financials", "005930", "--as-of", "2024-04-01"])
        self.assertEqual(code, 0, out)
        self.assertIn("개별/별도(OFS)", out)

    def test_no_report_by_as_of_is_no_data(self):
        code, out = self.run_cli(["financials", "005930", "--as-of", "2024-01-01"])
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("NO_DATA:"))

    def test_quarterly_report_selection(self):
        self.financials[("2024", "11014", "CFS")] = items("20241114000002")
        code, out = self.run_cli(["financials", "005930", "--report", "11014", "--as-of", "2025-01-15"])
        self.assertEqual(code, 0, out)
        self.assertIn("3분기보고서", out)

    def test_historical_disclosures_include_originals(self):
        code, out = self.run_cli(["disclosures", "005930", "--as-of", "2024-04-01"])
        self.assertEqual(code, 0, out)
        params = [p for e, p in self.calls if e == "list.json"][0]
        self.assertEqual((params["end_de"], params["last_reprt_at"]), ("20240401", "N"))
        self.assertNotIn("20250311", out)
        self.assertIn("정정 전 원공시 포함", out)


if __name__ == "__main__":
    unittest.main()
