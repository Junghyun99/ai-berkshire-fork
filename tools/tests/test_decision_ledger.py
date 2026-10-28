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


class _LedgerBase(unittest.TestCase):
    """임시 원장 + 가짜 종목 확인. 테스트 클래스들이 공유한다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("LEDGER", os.path.join(self.tmp.name, "l.csv")),
                            ("OUTCOMES", os.path.join(self.tmp.name, "o.csv")),
                            ("LESSONS", os.path.join(self.tmp.name, "lessons.md"))):
            p = mock.patch.object(dl, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(dl, "resolve_symbol", return_value=("005930.KS", "KRW", 55000.0))
        p.start()
        self.addCleanup(p.stop)

    def add(self, *extra, date_="2025-01-02", verdict="매수", ticker="005930"):
        return run_cli(["add", "--ticker", ticker, "--name", "삼성전자", "--skill", "investment-team",
                        "--verdict", verdict, "--conviction", "4", "--date", date_, *extra])


class LedgerTest(_LedgerBase):
    def test_add_records_market_benchmark_and_rejects_duplicate(self):
        # 오늘 작성한 리포트면 참고용 기록시점가(현재가)를 남긴다.
        code, out = self.add("--iv-low", "70000", "--iv-high", "90000", date_=date.today().isoformat())
        self.assertEqual(code, 0, out)
        row = dl._read(dl.LEDGER)[0]
        self.assertEqual((row["시장"], row["벤치마크"], row["기록시점가"]), ("KOSPI", "069500.KS", "55000"))
        code, out = self.add(date_=date.today().isoformat())
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



REPORT = """# 삼성전자 최종보고서

## 1. 한 문장 결론
**판단**: 관망 | **확신도**: ★★★★ | **내재가치**: 180,000~220,000원 | **반증 조건**: HBM 점유율 40% 미만

본문: 지금 매수는 아니다. 매수 판단은 가격이 내려오면 다시 본다.

예시(코드 블록 안은 무시):
```
**판단**: 매수 | **확신도**: ★★★★★ | **내재가치**: - | **반증 조건**: -
```

## 실행 정보
- 작성일: 2025-01-02
- 스킬: investment-team
- 실행 라벨: lab-a
- 데이터 출처·도구: DART(dart_data.py), 네이버 금융
"""


class LessonsTest(_LedgerBase):
    """회고 교훈을 종목 밖으로 모으고, 같은 종목 → 태그 → 시장 순, 오판·운 먼저 고른다."""

    def setUp(self):
        super().setUp()
        L = ["id", "기록일", "종목", "티커", "심볼", "시장", "판단", "확신도"]
        rows = [("a", "2025-01-02", "삼성전자", "005930", "005930.KS", "KOSPI", "매수", "4"),
                ("b", "2025-03-02", "SK하이닉스", "000660", "000660.KS", "KOSPI", "매수", "3"),
                ("c", "2025-05-02", "애플", "AAPL", "AAPL", "US", "회피", "2"),
                ("d", "2025-06-02", "네이버", "035420", "035420.KS", "KOSPI", "관망", "3")]
        dl._write(dl.LEDGER, dl.LEDGER_FIELDS, [dict(zip(L, r)) for r in rows])
        O = ["id", "구간", "알파", "논지상태", "회고", "교훈", "태그"]
        outs = [("a", "12M", "0.10", "유지", "알파 양수.", "실적 정점 전에 주가가 먼저 꺾인다", "메모리,사이클"),
                ("b", "12M", "-0.20", "훼손", "알파 음수.", "후행 신호로는 정점을 못 잡는다", "메모리 반도체"),
                ("b", "6M", "-0.05", "훼손", "알파 음수.", "후행 신호로는 정점을 못 잡는다", "메모리 반도체"),
                ("c", "12M", "0.15", "훼손", "회피했는데 올랐다. 해자 과소평가.", "", ""),
                ("d", "12M", "0.02", "불명", "", "", "플랫폼")]   # 회고·교훈 없음 → 제외
        dl._write(dl.OUTCOMES, dl.OUTCOME_FIELDS, [dict(zip(O, o)) for o in outs])

    def test_collect_dedupes_and_falls_back_to_note(self):
        ls = dl.collect_lessons(dl._read(dl.LEDGER), dl._read(dl.OUTCOMES))
        self.assertEqual(len(ls), 3)                       # b 의 같은 교훈은 한 번, d 는 빈 회고
        c = [l for l in ls if l["id"] == "c"][0]
        self.assertEqual((c["교훈"], c["원문"], c["분면"]), ("회피했는데 올랐다. 해자 과소평가.", "회고 원문", "오판"))

    def test_select_order_ticker_then_tag_then_market(self):
        ls = dl.collect_lessons(dl._read(dl.LEDGER), dl._read(dl.OUTCOMES))
        ids = [l["id"] for l in dl.select_lessons(ls, ticker="005930", tags=["메모리"], market="US")]
        self.assertEqual(ids, ["a", "b", "c"])             # 종목 → 태그(부분 일치) → 시장
        ids = [l["id"] for l in dl.select_lessons(ls, tags=["반도체"])]
        self.assertEqual(ids, ["b"])
        ids = [l["id"] for l in dl.select_lessons(ls)]     # 필터 없음: 오판(b·c, 최근 먼저) → 실력(a)
        self.assertEqual(ids, ["c", "b", "a"])

    def test_cli_lessons_and_no_match(self):
        code, out = run_cli(["lessons", "--tag", "메모리", "--limit", "1"])
        self.assertEqual(code, 0, out)
        self.assertIn("후행 신호로는 정점을 못 잡는다", out)
        self.assertNotIn("실적 정점 전에", out)            # limit 1
        code, out = run_cli(["lessons", "--tag", "바이오"])
        self.assertEqual(code, 3, out)

    def test_review_records_lesson_and_rewrites_file(self):
        code, out = run_cli(["review", "--id", "d", "--horizon", "12M", "--thesis-status", "불명",
                             "--note", "판단 불가.", "--lesson", "플랫폼 규제는 숫자보다 먼저 온다",
                             "--tags", "플랫폼, 규제 / 플랫폼"])
        self.assertEqual(code, 0, out)
        d = [o for o in dl._read(dl.OUTCOMES) if o["id"] == "d"][0]
        self.assertEqual((d["교훈"], d["태그"]), ("플랫폼 규제는 숫자보다 먼저 온다", "플랫폼,규제"))
        text = open(dl.LESSONS, encoding="utf-8").read()
        self.assertIn("## 오판 (2건)", text)
        self.assertIn("## 관망·논지 불명 (1건)", text)
        self.assertIn("플랫폼 규제는 숫자보다 먼저 온다", text)

    def test_old_outcomes_file_without_lesson_columns(self):
        old = [f for f in dl.OUTCOME_FIELDS if f not in ("교훈", "태그")]
        dl._write(dl.OUTCOMES, old, [{"id": "a", "구간": "12M", "알파": "0.1", "논지상태": "유지", "회고": "옛 회고"}])
        ls = dl.collect_lessons(dl._read(dl.LEDGER), dl._read(dl.OUTCOMES))
        self.assertEqual([l["교훈"] for l in ls], ["옛 회고"])


class ReportParseTest(unittest.TestCase):
    def test_label_line_parsed_and_code_block_and_prose_ignored(self):
        got = dl.parse_label(REPORT)
        self.assertEqual(got, {"판단": "관망", "확신도": 4, "내재가치하단": "180000",
                               "내재가치상단": "220000", "반증조건": "HBM 점유율 40% 미만"})

    def test_conflicting_or_missing_or_variant_verdict_is_refused(self):
        two = REPORT + "\n**판단**: 매수 | **확신도**: ★★★\n"
        with self.assertRaises(dl.ReportParseError):
            dl.parse_label(two)
        with self.assertRaises(dl.ReportParseError):
            dl.parse_label("# 결론\n지금은 매수다.\n")
        with self.assertRaises(dl.ReportParseError):
            dl.parse_label("**판단**: 조건부 매수 | **확신도**: ★★★\n")

    def test_fullwidth_colon_and_multi_company_filter(self):
        multi = ("**종목**: 텐센트 | **판단**：매수 | **확신도**: ★★★★ | **내재가치**: -\n"
                 "**종목**: 마오타이 | **판단**: 회피 | **확신도**: 2 | **내재가치**: 1500\n")
        self.assertEqual(dl.parse_label(multi, "텐센트")["판단"], "매수")
        got = dl.parse_label(multi, "마오타이")
        self.assertEqual((got["판단"], got["확신도"], got["내재가치하단"], got["내재가치상단"]),
                         ("회피", 2, "1500", "1500"))
        with self.assertRaises(dl.ReportParseError):
            dl.parse_label(multi, "엔비디아")

    def test_ambiguous_intrinsic_value_refused(self):
        with self.assertRaises(dl.ReportParseError):
            dl.parse_iv("10~20 또는 30")

    def test_run_info(self):
        self.assertEqual(dl.parse_run_info(REPORT)["실행 라벨"], "lab-a")
        self.assertEqual(dl.parse_run_info(REPORT)["스킬"], "investment-team")


class FromReportAddTest(_LedgerBase):
    def write_report(self, text=REPORT):
        path = os.path.join(self.tmp.name, "report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_add_from_report_fills_fields(self):
        code, out = run_cli(["add", "--ticker", "005930", "--name", "삼성전자", "--from-report", self.write_report()])
        self.assertEqual(code, 0, out)
        row = dl._read(dl.LEDGER)[0]
        self.assertEqual((row["판단"], row["확신도"], row["스킬"], row["기록일"], row["실행라벨"],
                          row["내재가치하단"], row["반증조건"]),
                         ("관망", "4", "investment-team", "2025-01-02", "lab-a", "180000", "HBM 점유율 40% 미만"))
        self.assertEqual(row["기록시점가"], "")  # 과거 작성일이면 오늘 가격을 기록하지 않음

    def test_cli_value_contradicting_report_is_refused(self):
        code, out = run_cli(["add", "--ticker", "005930", "--name", "삼성전자",
                             "--from-report", self.write_report(), "--verdict", "매수"])
        self.assertNotEqual(code, 0)
        self.assertIn("다릅니다", out)
        self.assertEqual(dl._read(dl.LEDGER), [])

    def test_unreadable_report_is_no_data(self):
        code, out = run_cli(["add", "--ticker", "005930", "--name", "삼성전자",
                             "--from-report", self.write_report("# 결론 없음\n")])
        self.assertEqual(code, _us_common.EXIT_NO_DATA)
        self.assertEqual(dl._read(dl.LEDGER), [])

    def test_run_label_from_env_and_summary_breakdown(self):
        with mock.patch.dict(os.environ, {"AI_BERKSHIRE_RUN_LABEL": "lab-b"}):
            self.add()
        self.add("--run-label", "lab-c", ticker="AAPL")
        rows = dl._read(dl.LEDGER)
        self.assertEqual([r["실행라벨"] for r in rows], ["lab-b", "lab-c"])
        stock = series("2024-12-20", 900, 50000, 50)
        with mock.patch.object(dl, "fetch_closes", side_effect=lambda s, a, b: [
                r for r in (series("2024-12-20", 900, 100, 0) if s in ("069500.KS", "SPY") else stock)
                if a <= r[0] <= b]):
            run_cli(["settle"])
        code, out = run_cli(["summary"])
        self.assertIn("실행 라벨별", out)
        self.assertIn("lab-b", out)


if __name__ == "__main__":
    unittest.main()
