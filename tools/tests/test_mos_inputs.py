"""요구 안전마진 입력 오프라인 테스트 — 순수 함수와 원장 일괄 계산(가짜 수집기).

실행: python3 -m unittest discover -s tools/tests -v
"""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import mos_inputs as mi  # noqa: E402


class PureTest(unittest.TestCase):
    def test_drawdown_peak_to_trough(self):
        # 기아 영업이익(조원): 2016 2.46 → 2017 0.66 이 최대 하락 73.1%
        s = {2016: 2.46148, 2017: 0.662226, 2018: 1.157475, 2019: 2.00968, 2020: 2.066457, 2021: 5.065685,
             2022: 7.23312, 2023: 11.607873, 2024: 12.667139, 2025: 9.078148}
        dd = mi.earnings_drawdown(s)
        self.assertEqual((dd["하락률"], dd["고점연도"], dd["저점연도"], dd["연도수"]), (73.1, 2016, 2017, 10))
        self.assertEqual(mi.u_e_from(dd), 21.9)

    def test_drawdown_uses_last_ten_years_and_running_peak(self):
        s = {2010: 100, 2011: 1}                                    # 10년 밖
        s.update({y: 10 + y - 2012 for y in range(2012, 2021)})     # 꾸준히 증가
        s[2021] = 15                                                # 2020 고점 18 → 15
        dd = mi.earnings_drawdown(s)
        self.assertEqual((dd["연도수"], dd["고점연도"], dd["저점연도"], dd["하락률"]), (10, 2020, 2021, 16.7))
        self.assertEqual(mi.earnings_drawdown({2020: 1, 2021: 2, 2022: 3, 2023: 4, 2024: 5})["하락률"], 0.0)

    def test_loss_year_is_full_drawdown_and_short_history_caps(self):
        dd = mi.earnings_drawdown({2019: 5, 2020: 8, 2021: -1, 2022: 6, 2023: 7})
        self.assertEqual((dd["하락률"], dd["고점연도"], dd["저점연도"]), (100.0, 2020, 2021))
        self.assertEqual(mi.u_e_from(dd), 30.0)
        short = mi.earnings_drawdown({2023: 1, 2024: 2, 2025: 3})
        self.assertEqual(mi.u_e_from(short), 30.0)                  # 5개 해 미만 → 상한
        self.assertEqual(mi.u_e_from(mi.earnings_drawdown({})), 30.0)

    def test_leverage_penalty(self):
        self.assertEqual(mi.leverage_penalty(100, 10, False), (10.0, 0.0))
        self.assertEqual(mi.leverage_penalty(50, 10, False), (5.0, 5.0))
        self.assertEqual(mi.leverage_penalty(20, -10, False), (2.0, 10.0))    # 부호와 무관
        self.assertEqual(mi.leverage_penalty(100, 0, False), (None, 0.0))     # 무차입
        self.assertEqual(mi.leverage_penalty(-5, 10, False), (-0.5, 10.0))    # 영업적자
        self.assertEqual(mi.leverage_penalty(1, 100, True), (None, 0.0))      # 금융업

    def test_financial_leverage_penalty(self):
        self.assertEqual(mi.financial_penalty(17, 10), (1.7, 0.0))           # 버크셔형
        self.assertEqual(mi.financial_penalty(68, 10), (6.8, 5.0))           # 손해보험
        self.assertEqual(mi.financial_penalty(135, 10), (13.5, 10.0))        # 은행 지주
        self.assertEqual(mi.financial_penalty(100, 10), (10.0, 10.0))        # 경계 10배는 +10
        self.assertEqual(mi.financial_penalty(None, 10), (None, 10.0))       # 미확보 → 보수적
        self.assertEqual(mi.financial_penalty(10, -1), (None, 10.0))         # 자본잠식
        info = {"metric": "지배순이익", "u_e": 1.7, "coverage": None, "cov_year": 2025, "L": 10.0, "financial": True,
                "leverage": 13.5, "lev_year": 2025, "source": "DART",
                "drawdown": {"하락률": 5.8, "고점연도": 2021, "저점연도": 2022, "연도수": 10, "초기적자제외": ""}}
        self.assertIn("**재무 위험**: 금융업 레버리지(총자산/자기자본) 13.5배(2025) → L 10", mi.inputs_line(info))

    def test_required_mos_and_lines(self):
        self.assertEqual(mi.u_v_from(95000, 130000), 15.6)
        self.assertEqual(mi.required_mos(15.6, 21.9, 0), 31.9)                # max 를 쓴다(합산 아님)
        self.assertEqual(mi.required_mos(2, 1, 0), 15.0)                      # 하한
        self.assertEqual(mi.required_mos(40, 30, 10), 45.0)                   # 상한
        self.assertEqual(mi.tranche_mos(31.9), (21.9, 31.9, 41.9))
        line = mi.margin_line(88200, 95000, 130000, 21.9, 0, "원")
        self.assertIn("기준가 88,200원 · 중앙 112,500원 → 21.6%", line)
        self.assertIn("**요구 안전마진**: 10 + max(U_v 15.6, U_e 21.9) + L 0 = 31.9%", line)
        info = {"metric": "영업이익", "drawdown": {"하락률": 73.1, "고점연도": 2016, "저점연도": 2017, "연도수": 10},
                "u_e": 21.9, "coverage": 65.72, "cov_year": 2025, "L": 0.0, "financial": False, "source": "DART"}
        self.assertEqual(mi.inputs_line(info), "**이익 변동**: 영업이익 최대 하락 73.1% (2016→2017, 10개 해, DART) "
                                               "→ U_e 21.9% | **재무 위험**: 이자보상배율 65.72배(2025) → L 0")

    def test_market_and_manual_input(self):
        self.assertEqual([mi.market_of(t) for t in ("000270", "005930.KS", "KO", "6871.T")],
                         ["KR", "KR", "US", "OTHER"])
        other = mi.compute("6871.T", "2026-10-31")
        self.assertEqual((other["u_e"], other.get("missing")), (30.0, True))
        man = mi.compute("6871.T", "2026-10-31", u_e=18, l_pen=5, note="닛케이 10년 영업이익")
        self.assertEqual((man["u_e"], man["L"]), (18.0, 5.0))
        self.assertIn("직접 계산 U_e 18%", mi.inputs_line(man))


class StartupAndAdjustmentTest(unittest.TestCase):
    def test_startup_losses_excluded_after_five_profitable_years(self):
        s = {2016: -3, 2017: -2, 2018: -1, 2019: 1, 2020: 2, 2021: 3, 2022: 4, 2023: 3.6}
        dd = mi.earnings_drawdown(s)
        self.assertEqual((dd["초기적자제외"], dd["연도수"], dd["하락률"]), ("2016~2018", 5, 10.0))
        # 흑자 4개 해뿐이면 제외하지 않는다
        self.assertEqual(mi.earnings_drawdown({2016: -1, 2017: 1, 2018: 2, 2019: 3, 2020: 4})["하락률"], 100.0)
        # 흑자였다가 적자로 돌아선 해는 초기 적자가 아니다(고점은 구간 밖까지 본다)
        cyc = {y: 10.0 for y in range(2005, 2026)}
        cyc[2016] = -1
        dd = mi.earnings_drawdown(cyc)
        self.assertEqual((dd["하락률"], dd["고점연도"], dd["저점연도"], dd["초기적자제외"]), (100.0, 2005, 2016, ""))
        # 데이터 첫 해의 적자가 계산 구간 밖이면 규칙을 쓰지 않는다(표시도 없음)
        old = {2009: -1.0}
        old.update({y: 5.0 for y in range(2010, 2026)})
        self.assertEqual(mi.earnings_drawdown(old)["초기적자제외"], "")
        # 첫 흑자 이후 다시 적자면 제외하지 않는다
        self.assertEqual(mi.earnings_drawdown({2014: -1, 2015: 1, 2016: 2, 2017: 3, 2018: -1, 2019: 4,
                                                2020: 5})["하락률"], 100.0)

    def test_adjustments_file_recurring_needs_all_years(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "adj.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(mi.ADJ_FIELDS)
                for y in range(2016, 2026):
                    w.writerow(["AVGO", "인수 무형자산 상각", y, 3, "10-K"])
                w.writerow(["AVGO", "영업권·무형자산 손상", 2020, 5, "10-K, 그 외 연도 없음"])
                w.writerow(["XYZ", "인수 무형자산 상각", 2025, 1, "10-K"])
            adj = mi.load_adjustments("avgo", path)
            series = {y: 10.0 for y in range(2016, 2026)}
            series[2016], series[2020] = -1.0, 2.0
            out, used, skipped = mi.apply_adjustments(series, adj)
            self.assertEqual((out[2016], out[2020], out[2025]), (2.0, 10.0, 13.0))
            self.assertEqual((used, skipped), (["인수 무형자산 상각", "영업권·무형자산 손상"], {}))
            # 반복 항목인데 한 해만 있으면 조정하지 않는다
            out, used, skipped = mi.apply_adjustments({y: 1.0 for y in range(2016, 2026)},
                                                      mi.load_adjustments("XYZ", path))
            self.assertEqual(used, [])
            self.assertIn("인수 무형자산 상각", skipped)
            with open(path, "a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(["AVGO", "구조조정 비용", 2020, 1, "10-K"])
            with self.assertRaises(SystemExit):                       # 허용 목록 밖 항목은 거부
                mi.load_adjustments("AVGO", path)

    def test_adjusted_inputs_line_has_evidence(self):
        info = {"metric": "조정 영업이익(인수 무형자산 상각)", "u_e": 0.1, "coverage": 7.94, "cov_year": 2025, "L": 5.0,
                "financial": False, "source": "SEC(USD)",
                "drawdown": {"하락률": 0.2, "고점연도": 2018, "저점연도": 2019, "연도수": 10, "초기적자제외": ""},
                "adjustments": {"인수 무형자산 상각": {"연도별": {2016: 2.64e9}, "출처": ["10-K"]}}}
        line = mi.inputs_line(info)
        self.assertIn("**이익 변동**: 조정 영업이익(인수 무형자산 상각) 최대 하락 0.2%", line)
        self.assertIn("**조정 근거**: 인수 무형자산 상각: 2016 +2.64B (출처: 10-K)", line)


class LedgerTest(unittest.TestCase):
    def test_ledger_rows_status_and_failures(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id", "기록일", "종목", "티커", "통화", "판단", "기록시점가", "내재가치하단", "내재가치상단"])
                w.writerow(["a", "2026-11-20", "기아", "000270", "KRW", "관망", "88200", "95000", "130000"])
                w.writerow(["b", "2026-11-20", "싼곳", "AAA", "USD", "관망", "60", "95000", "130000"])
                w.writerow(["c", "2026-11-20", "실패", "BAD", "USD", "관망", "10", "10", "20"])
                w.writerow(["d", "2026-11-20", "무가치", "AAA", "USD", "관망", "10", "", ""])

            def fake(ticker, as_of):
                if ticker == "BAD":
                    raise ConnectionError("down")
                return {"metric": "영업이익", "drawdown": {"하락률": 73.1, "고점연도": 2016, "저점연도": 2017,
                                                       "연도수": 10}, "u_e": 21.9, "coverage": 65.7, "L": 0.0,
                        "financial": False, "source": "TEST"}
            rows = {r["id"]: r for r in mi.ledger_rows(path, fake, "2026-11-27")}
        a = rows["a"]
        self.assertEqual((a["U_v"], a["요구안전마진"], a["1차"], a["현재안전마진"], a["상태"]),
                         (15.6, 31.9, 87900.0, 21.6, "C 가격 대기"))           # 88,200 > 1차 87,900
        self.assertEqual(rows["b"]["상태"], "A 요구 충족")
        self.assertEqual((rows["c"]["상태"], rows["c"]["비고"]), ("계산 실패", "down"))
        self.assertEqual(rows["d"]["상태"], "내재가치 없음")


if __name__ == "__main__":
    unittest.main()
