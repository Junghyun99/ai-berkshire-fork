"""판단 원장 오프라인 테스트 — 가격 조회를 픽스처로 대체.

실행: python3 -m unittest discover -s tools/tests -v
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import _us_common  # noqa: E402
import decision_ledger as dl  # noqa: E402


def series(start: str, days: int, first: float, step: float):
    """평일만 있는 가격 시계열 [(날짜, 종가, 수정종가)]."""
    d = date.fromisoformat(start)
    rows, price = [], first
    while len(rows) < days:
        if d.weekday() < 5:
            rows.append((d.isoformat(), price, price))
            price += step
        d += timedelta(days=1)
    return rows


def run_cli(argv):
    out = io.StringIO()
    code = 0
    with mock.patch.object(sys, "argv", ["prog"] + argv), contextlib.redirect_stdout(out):
        try:
            _us_common.run(dl.main)
        except SystemExit as e:
            # 입력 오류는 SystemExit(메시지)로 끝난다: 메시지는 stderr로 가므로 출력에 합쳐 검사한다.
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                out.write(e.code)
    return code, out.getvalue()


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("LEDGER", os.path.join(self.tmp.name, "l.csv")),
                            ("OUTCOMES", os.path.join(self.tmp.name, "o.csv"))):
            p = mock.patch.object(dl, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(dl, "resolve_symbol", return_value=("005930.KS", "KRW", 55000.0))
        p.start()
        self.addCleanup(p.stop)

    def add(self, *extra, date_="2025-01-02", verdict="매수", ticker="005930"):
        return run_cli(["add", "--ticker", ticker, "--name", "삼성전자", "--skill", "investment-team",
                        "--verdict", verdict, "--conviction", "4", "--date", date_, *extra])

    def test_add_records_market_benchmark_and_rejects_duplicate(self):
        code, out = self.add("--iv-low", "70000", "--iv-high", "90000")
        self.assertEqual(code, 0, out)
        row = dl._read(dl.LEDGER)[0]
        self.assertEqual((row["시장"], row["벤치마크"], row["기록시점가"]), ("KOSPI", "069500.KS", "55000"))
        code, out = self.add()
        self.assertNotEqual(code, 0)
        self.assertIn("이미 기록된 판단", out)
        self.assertEqual(len(dl._read(dl.LEDGER)), 1)

    def test_add_rejects_bad_verdict_and_future_date(self):
        self.assertNotEqual(self.add(verdict="강력매수")[0], 0)
        future = (date.today() + timedelta(days=3)).isoformat()
        self.assertNotEqual(self.add(date_=future)[0], 0)

    def test_entry_is_next_session_and_scoring(self):
        self.add("--iv-low", "70000", "--iv-high", "90000")
        row = dl._read(dl.LEDGER)[0]
        stock = series("2024-12-20", 300, 50000, 100)
        bench = series("2024-12-20", 300, 100, 0)  # 벤치마크 수익률 0 → 알파 = 수익률
        r = dl.evaluate(row, "3M", stock, bench)
        self.assertEqual(r["진입일"], "2025-01-03")  # 기록일 다음 거래일
        self.assertGreaterEqual(r["평가일"], "2025-04-03")
        self.assertEqual(r["방향적중"], "적중")
        self.assertEqual(r["수익률"], r["알파"])
        self.assertNotIn("e+", r["진입가"])

    def test_not_settled_before_window_has_traded(self):
        self.add()
        row = dl._read(dl.LEDGER)[0]
        stock = series("2024-12-20", 40, 50000, 100)  # 3개월 전에 끝남
        self.assertIsNone(dl.evaluate(row, "3M", stock, stock))
        full = series("2024-12-20", 300, 50000, 100)
        short_bench = series("2024-12-20", 40, 100, 0)  # 벤치마크가 청산일까지 거래 안 됨
        self.assertIsNone(dl.evaluate(row, "3M", full, short_bench))

    def test_hold_verdict_has_no_direction_and_avoid_scores_inverse(self):
        self.add(verdict="관망")
        self.add(verdict="회피", ticker="AAPL")
        rows = dl._read(dl.LEDGER)
        up = series("2024-12-20", 300, 100, 1)
        flat = series("2024-12-20", 300, 100, 0)
        self.assertEqual(dl.evaluate(rows[0], "3M", up, flat)["방향적중"], "-")
        self.assertEqual(dl.evaluate(rows[1], "3M", up, flat)["방향적중"], "빗나감")

    def test_settle_review_show_summary(self):
        self.add("--thesis", "메모리 업사이클", "--falsifier", "HBM 퀄 실패")
        stock = series("2024-12-20", 900, 50000, 50)
        bench = series("2024-12-20", 900, 100, 0)
        with mock.patch.object(dl, "fetch_closes", side_effect=lambda s, a, b: [
                r for r in (stock if s == "005930.KS" else bench) if a <= r[0] <= b]):
            code, out = run_cli(["settle"])
        self.assertEqual(code, 0, out)
        horizons = [o["구간"] for o in dl._read(dl.OUTCOMES)]
        self.assertIn("12M", horizons)
        # 두 번째 정산은 이미 정산된 구간을 다시 쓰지 않는다.
        with mock.patch.object(dl, "fetch_closes", side_effect=lambda s, a, b: [
                r for r in (stock if s == "005930.KS" else bench) if a <= r[0] <= b]):
            run_cli(["settle"])
        self.assertEqual(len(dl._read(dl.OUTCOMES)), len(horizons))

        rid = dl._read(dl.LEDGER)[0]["id"]
        code, _ = run_cli(["review", "--id", rid, "--horizon", "12M", "--thesis-status", "유지",
                           "--note", "알파 양수. 논지 유지.\n교훈 하나."])
        self.assertEqual(code, 0)
        code, out = run_cli(["show", "삼성전자"])
        self.assertIn("반증 조건: HBM 퀄 실패", out)
        self.assertIn("회고: 알파 양수. 논지 유지. 교훈 하나.", out)
        code, out = run_cli(["summary"])
        self.assertIn("매수: n=1, 방향 적중 100%", out)
        self.assertIn("실력 1", out)

    def test_settle_price_failure_is_unavailable_and_not_written(self):
        self.add()
        with mock.patch.object(dl, "fetch_closes", side_effect=_us_common.UnavailableError("HTTP 500")):
            code, out = run_cli(["settle"])
        self.assertEqual(code, _us_common.EXIT_UNAVAILABLE)
        self.assertEqual(dl._read(dl.OUTCOMES), [])

    def test_review_without_settlement_is_no_data(self):
        self.add()
        rid = dl._read(dl.LEDGER)[0]["id"]
        code, _ = run_cli(["review", "--id", rid, "--horizon", "3M", "--thesis-status", "유지", "--note", "x"])
        self.assertEqual(code, _us_common.EXIT_NO_DATA)

    def test_add_months_clamps_month_end(self):
        self.assertEqual(dl.add_months("2025-11-30", 3), "2026-02-28")
        self.assertEqual(dl.add_months("2025-01-31", 1), "2025-02-28")

    def test_iv_position(self):
        self.assertEqual(dl.iv_position(60000, "70000", "90000"), "하단 미만")
        self.assertEqual(dl.iv_position(80000, "70000", "90000"), "범위 안")
        self.assertEqual(dl.iv_position(95000, "70000", "90000"), "상단 초과")
        self.assertEqual(dl.iv_position(95000, "", ""), "-")


if __name__ == "__main__":
    unittest.main()
