"""실행 상태(중단 후 이어서 실행) 오프라인 테스트 — 임시 reports 폴더에서 단계 기록·검증·되돌림을 확인한다.

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
import report_check as rc  # noqa: E402
import run_state as rs  # noqa: E402

LABEL = "**판단**: 관망 | **확신도**: ★★★ | **내재가치**: 180,000~200,000원 | **반증 조건**: x"


def run_cli(argv):
    out, code = io.StringIO(), 0
    with mock.patch.object(sys, "argv", ["prog"] + argv), contextlib.redirect_stdout(out):
        try:
            _us_common.run(rs.main)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                out.write(e.code)
    return code, out.getvalue()


class RunStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(rs, "REPORTS", self.tmp.name)
        p.start()
        self.addCleanup(p.stop)
        self.dir = os.path.join(self.tmp.name, "테스트")
        os.makedirs(self.dir)
        self.cmd = lambda *a: run_cli(list(a[:1]) + ["--company", "테스트"] + list(a[1:]))
        self.assertEqual(self.cmd("start", "--ticker", "005930")[0], 0)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def state(self):
        with open(rs.state_path("테스트", "investment-team"), encoding="utf-8") as f:
            return json.load(f)

    def finish_inputs(self):
        for key in ("lessons", "factsheet"):
            self.cmd("put", "--key", key, "--file", self.write(f"{key}.txt", f"{key} 내용"))
        self.assertEqual(self.cmd("done", "--step", "context")[0], 0)
        self.assertEqual(self.cmd("done", "--step", "factsheet")[0], 0)

    def views(self):
        for name in rc.TEAM_VIEWS:
            self.write(name, "# 관점\n\n**관점 판단**: 관망 — 이유")
        for step in ("view-duan", "view-buffett", "view-munger", "view-lilu"):
            self.assertEqual(self.cmd("done", "--step", step)[0], 0)

    def test_start_twice_is_refused_unless_force(self):
        code, out = self.cmd("start", "--ticker", "005930")
        self.assertEqual(code, 1)
        self.assertIn("이미 진행 중", out)
        self.assertEqual(self.cmd("start", "--ticker", "005930", "--force")[0], 0)

    def test_inputs_must_be_put_before_done_and_get_returns_same_text(self):
        code, out = self.cmd("done", "--step", "factsheet")
        self.assertEqual(code, 1)
        self.assertIn("put --key factsheet", out)
        self.finish_inputs()
        code, out = self.cmd("get", "--key", "factsheet")
        self.assertEqual((code, out), (0, "factsheet 내용"))
        self.assertEqual(self.cmd("get", "--key", "없음")[0], 3)

    def test_truncated_view_is_not_done_and_parallel_views_listed(self):
        self.finish_inputs()
        code, out = self.cmd("next")
        self.assertEqual(out.split(), ["view-duan", "view-buffett", "view-munger", "view-lilu"])
        self.write(rc.TEAM_VIEWS[2], "# 멍거 관점\n\n## 1. 산업 구도\n표 작성 중")   # 저장 도중 끊김
        code, out = self.cmd("done", "--step", "view-munger")
        self.assertEqual(code, 1)
        self.assertIn("중간에 끊긴 파일", out)
        self.assertEqual(self.state()["steps"]["view-munger"]["status"], "대기")

    def test_fail_twice_suggests_fallback(self):
        self.cmd("fail", "--step", "view-munger", "--error", "API 오류")
        code, out = self.cmd("fail", "--step", "view-munger", "--error", "API 오류")
        self.assertIn("대리 작성", out)
        code, out = self.cmd("status")
        self.assertIn("2번 실패했습니다", out)
        self.assertEqual(self.state()["steps"]["view-munger"]["attempts"], 2)

    def test_redoing_earlier_stage_resets_later_stages_only(self):
        self.finish_inputs()
        self.views()
        self.write("05-교차반론.md", "\n".join(f"**관점 판단**: 관망 — {i}" for i in range(4)))
        self.assertEqual(self.cmd("done", "--step", "rebuttal")[0], 0)
        self.write("최종보고서.md", LABEL)
        self.assertEqual(self.cmd("done", "--step", "final")[0], 0)
        code, out = self.cmd("done", "--step", "view-buffett")         # 관점 보고서를 다시 씀
        self.assertIn("재실행 필요: rebuttal, final", out)
        steps = self.state()["steps"]
        self.assertEqual((steps["rebuttal"]["status"], steps["final"]["status"]), ("대기", "대기"))
        self.assertEqual(steps["view-duan"]["status"], "끝남")           # 같은 묶음은 그대로
        self.assertEqual(self.cmd("next")[1].strip(), "rebuttal")

    def test_status_flags_changed_artifact_and_finish_requires_all(self):
        self.finish_inputs()
        self.views()
        with open(os.path.join(self.dir, rc.TEAM_VIEWS[0]), "a", encoding="utf-8") as f:
            f.write("\n추가 수정")
        code, out = self.cmd("status")
        self.assertIn("끝난 뒤 산출물이 바뀜", out)
        code, out = self.cmd("finish")
        self.assertEqual(code, 1)
        self.assertIn("rebuttal", out)

    def test_ledger_step_and_finish_removes_state(self):
        st = self.state()
        for k in st["steps"]:
            st["steps"][k]["status"] = "끝남"
        st["steps"]["ledger"]["status"] = "대기"
        rs._save(st)
        rid = f"{st['started'][:10]}-005930-investment-team"
        with mock.patch.object(rs.dl, "_read", return_value=[]):
            code, out = self.cmd("done", "--step", "ledger")
        self.assertEqual(code, 1)
        self.assertIn(rid, out)
        with mock.patch.object(rs.dl, "_read", return_value=[{"id": rid}]):
            self.assertEqual(self.cmd("done", "--step", "ledger")[0], 0)
        self.assertEqual(self.cmd("finish")[0], 0)
        self.assertFalse(os.path.exists(rs.state_path("테스트", "investment-team")))
        self.assertEqual(self.cmd("status")[0], 3)

    def test_unknown_step_is_refused(self):
        code, out = self.cmd("done", "--step", "view-graham")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
