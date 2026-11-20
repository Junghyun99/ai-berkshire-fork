"""보고서 형식 검사 오프라인 테스트 — 임시 폴더에 보고서를 만들어 검사한다.

실행: python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import report_check as rc  # noqa: E402

LABEL = "**판단**: 관망 | **확신도**: ★★★ | **내재가치**: 180,000~200,000원 | **반증 조건**: 고정가 하락"
PLAN = ("**실행 계획**: 비중 상한 5% | **분할 매수**: 161,500원 1.5% / 142,500원 1.5% / 123,500원 2% | "
        "**축소 검토**: 240,000원 이상 또는 반증 조건 발생 | **현재 상태**: 대기")
RUN_INFO = """## 실행 정보
- 작성일: 2026-10-28
- 스킬: {skill}
- 데이터 시점: 2026-10-27
- 데이터 출처·도구: DART, 팩트시트
- 표본 검사: report_audit 13건 — 통과 13
"""


def final_report(skill="investment-team", label=LABEL, run_info=None, extra="", plan=PLAN):
    return f"""# 테스트 최종보고서

## 1. 한 문장 결론
{label}

## 5.5 판정 근거
- 결정한 논거

## 7. 최종 투자 제안
{plan}

{extra}
## 부록: 팩트시트
| 항목 | 값 |

{RUN_INFO.format(skill=skill) if run_info is None else run_info}"""


class ReportCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def team(self, views=("관망", "관망", "관망", "관망"), ruling="약세 우세 — 가격: 안전마진 부족", turns=4, legacy=None):
        for name, v in zip(rc.TEAM_VIEWS, views):
            self.write(name, f"# 관점\n본문\n\n**관점 판단**: {v} — 이유")
        if legacy is not None:  # 이전 형식(교차 반론)
            self.write(rc.LEGACY_REBUTTAL_FILE,
                       "\n".join(f"**최종**: **관점 판단**: 관망 유지 — 이유 {i}" for i in range(legacy)))
        else:
            heads = ["### 강세 1라운드", "### 약세 1라운드", "### 강세 2라운드", "### 약세 2라운드"][:turns]
            body = "\n\n".join(f"{h}\n논거" for h in heads)
            self.write(rc.DEBATE_FILE, f"# 토론\n\n{body}\n\n**강세 최종 주장**: 싸다 | 틀리게 되는 조건: X\n"
                                       f"**약세 최종 주장**: 비싸다 | 틀리게 되는 조건: Y\n\n## Team Lead 판정\n"
                                       + (f"**토론 판정**: {ruling}\n" if ruling else ""))
        self.write("README.md", "# 개요")

    def debate(self, final_line=PLAN):
        # 기준선 줄(첫 줄)과 Team Lead 결정 줄(마지막 줄). 최종보고서와 비교하는 것은 마지막 줄이다.
        self.write("06-리스크토론-비중.md", f"## 기준선\n{PLAN}\n\n## 결정\n{final_line}\n")

    def marks(self, c):
        return [m for m, _ in c.items]

    def test_complete_team_report_passes(self):
        self.team()
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report()))
        self.assertFalse(c.failed, c.items)
        self.assertNotIn("⚠️", self.marks(c))

    def test_missing_view_line_and_rebuttal_fail(self):
        self.team(views=("관망", "관망", "강력매수", "관망"), legacy=3)
        os.remove(os.path.join(self.tmp.name, rc.TEAM_VIEWS[0]))
        c = rc.check(self.write("최종보고서.md", final_report()))
        msgs = " ".join(m for _, m in c.items)
        self.assertTrue(c.failed)
        self.assertIn("관점 보고서가 없습니다: 01-", msgs)
        self.assertIn("'강력매수' 은 매수/관망/회피가 아닙니다", msgs)
        self.assertIn("관점 판단이 4개 필요(찾은 것 3개", msgs)

    def test_legacy_rebuttal_file_warns_but_passes(self):
        self.team(legacy=4)
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report()))
        self.assertFalse(c.failed, c.items)
        self.assertIn("이전 형식", " ".join(m for _, m in c.items))

    def test_debate_missing_turns_and_ruling_fail(self):
        self.team(turns=3, ruling=None)
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report()))
        msgs = " ".join(m for _, m in c.items)
        self.assertTrue(c.failed)
        self.assertIn("`### 약세 2라운드` 절이 없습니다", msgs)
        self.assertIn("**토론 판정**", msgs)

    def test_ruling_must_match_verdict(self):
        # 강세 우세인데 관망 → 반려(관망으로 숨는 것을 막는다)
        self.team(ruling="강세 우세 — 하방 가정 과도")
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report()))
        self.assertTrue(c.failed)
        self.assertIn("토론 판정 '강세 우세' 인데 결론 판단이 '관망'", " ".join(m for _, m in c.items))
        # 강세 우세 + 매수 → 통과
        c = rc.check(self.write("최종보고서.md", final_report(label=LABEL.replace("관망", "매수"))))
        self.assertFalse(c.failed, c.items)
        # 균형 + 관망 → 통과, 약세 우세(영구 손실) + 관망 → 반려
        self.team(ruling="균형 — 양측 논거 상쇄")
        self.assertFalse(rc.check(self.write("최종보고서.md", final_report())).failed)
        self.team(ruling="약세 우세 — 영구 손실 경로 확인")
        self.assertTrue(rc.check(self.write("최종보고서.md", final_report())).failed)

    def test_bear_ruling_without_basis_warns(self):
        self.team(ruling="약세 우세 — 근거 표기 없음")
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report()))
        self.assertFalse(c.failed, c.items)
        self.assertIn("약세 우세의 근거", " ".join(m for _, m in c.items))

    def test_label_and_run_info_errors(self):
        self.team()
        bad_run = RUN_INFO.format(skill="investment-team").replace(
            "report_audit 13건 — 통과 13", "report_audit 결과는 출고 절차에서 기록").replace("- 데이터 시점: 2026-10-27\n", "")
        c = rc.check(self.write("최종보고서.md", final_report(label="**판단**: 강력매수 | **확신도**: ★★", run_info=bad_run)))
        msgs = " ".join(m for _, m in c.items)
        self.assertIn("매수/관망/회피 중 하나가 아닙니다", msgs)
        self.assertIn("빠진 줄: 데이터 시점", msgs)
        self.assertIn("표본 검사 결과가 아직 없습니다", msgs)

    def test_free_form_audit_placeholder_fails(self):
        # 정해진 자리표시 문구가 아니어도 판정어·숫자가 없으면 결과가 아니다
        run = RUN_INFO.format(skill="investment-team").replace(
            "report_audit 13건 — 통과 13", "(9단계 결과로 채운다)")
        c = rc.check(self.write("최종보고서.md", final_report(run_info=run)))
        self.assertIn("표본 검사 결과가 아직 없습니다", " ".join(m for _, m in c.items))

    def test_run_info_must_be_last_and_code_block_label_ignored(self):
        text = final_report(skill="investment-research", label="```\n" + LABEL + "\n```") + "\n## 덧붙임\n내용\n"
        c = rc.check(self.write("r.md", text))
        msgs = " ".join(m for _, m in c.items)
        self.assertIn("'## 실행 정보' 뒤에 다른 절이 있습니다", msgs)
        self.assertIn("결론 라벨 줄을 찾지 못했습니다", msgs.replace("(**판단**: 매수|관망|회피 ...)", ""))

    def test_research_needs_appendix_but_not_team_files(self):
        text = final_report(skill="investment-research").replace("## 부록: 팩트시트\n", "## 부록\n")
        c = rc.check(self.write("r.md", text))
        msgs = " ".join(m for _, m in c.items)
        self.assertIn("'## 부록: 팩트시트' 절이 없습니다", msgs)
        self.assertNotIn("관점 보고서", msgs)

    def test_checklist_multi_company_labels(self):
        labels = ("**종목**: 텐센트 | " + LABEL + "\n\n**종목**: 알리바바 | " + LABEL.replace("관망", "회피"))
        c = rc.check(self.write("c.md", final_report(skill="investment-checklist", label=labels)))
        oks = [m for mark, m in c.items if mark == "✅"]
        self.assertTrue(any("(텐센트): 관망" in m for m in oks))
        self.assertTrue(any("(알리바바): 회피" in m for m in oks))
        self.assertFalse(c.failed, c.items)

    def test_plan_line_missing_mismatched_or_malformed(self):
        self.team()
        # 06 없음 + 실행 계획 없음 → 7.5단계 이전 형식(경고)
        c = rc.check(self.write("최종보고서.md", final_report(plan="")))
        self.assertFalse(c.failed, c.items)
        self.assertTrue(any("7.5단계 리스크 토론 이전" in m for mark, m in c.items if mark == "⚠️"))
        # 06 있음 + 최종 줄 다름 → 반려
        self.debate(final_line=PLAN.replace("비중 상한 5%", "비중 상한 3%"))
        c = rc.check(self.write("최종보고서.md", final_report()))
        self.assertTrue(any("실행 계획이 다릅니다" in m for _, m in c.items))
        # 분할 매수 합계가 상한 초과 → 반려
        bad = PLAN.replace("비중 상한 5%", "비중 상한 4%")
        self.debate(final_line=bad)
        c = rc.check(self.write("최종보고서.md", final_report(plan=bad)))
        self.assertTrue(any("비중 상한 4% 를 넘습니다" in m for _, m in c.items))

    def test_style_warnings_do_not_fail(self):
        self.team()
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report(extra="점수 ★★★☆. 명백히 싸다.\n")))
        self.assertFalse(c.failed)
        msgs = " ".join(m for mark, m in c.items if mark == "⚠️")
        self.assertIn("반 별", msgs)
        self.assertIn("'명백히'", msgs)

    def test_skill_argument_mismatch_fails(self):
        c = rc.check(self.write("r.md", final_report(skill="investment-research")), "investment-checklist")
        self.assertTrue(any("스킬 'investment-research' 과 --skill" in m for _, m in c.items))


if __name__ == "__main__":
    unittest.main()
