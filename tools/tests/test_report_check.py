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
        "**축소 검토**: 240,000원 이상 또는 반증 조건 발생 | **현재 상태**: 대기 | **불확실성 반영**: 안전마진")
REQ = " | **요구 안전마진**: 10 + max(U_v 5.3, U_e 15) + L 0 = 25%"
INPUTS = ("**이익 변동**: 영업이익 최대 하락 50% (2019→2020, 10개 해, DART) → U_e 15% | "
          "**재무 위험**: 이자보상배율 20배(2025) → L 0")
FORMULA = "**내재가치 산식**: A 일반(2단계 오너어닝스 DCF) | 비관 150,000 / 중립 180,000 / 낙관 220,000 | 범위 165,000~200,000 KRW"
MARGIN = "**안전마진**: 기준가 175,000원 · 중앙 190,000원 → 7.9%" + REQ + "\n" + INPUTS + "\n" + FORMULA
RUN_INFO = """## 실행 정보
- 작성일: 2026-10-28
- 스킬: {skill}
- 데이터 시점: 2026-10-27
- 데이터 출처·도구: DART, 팩트시트
- 표본 검사: report_audit 13건 — 통과 13
"""


def final_report(skill="investment-team", label=LABEL, run_info=None, extra="", plan=PLAN, margin=MARGIN):
    return f"""# 테스트 최종보고서

## 1. 한 문장 결론
{label}

## 5.5 판정 근거
- 결정한 논거
{margin}

## 7. 최종 투자 제안
{plan}

{extra}
## 부록: 팩트시트
| 항목 | 값 |

{RUN_INFO.format(skill=skill) if run_info is None else run_info}"""


class _Base(unittest.TestCase):
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



class ReportCheckTest(_Base):
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
        # 근거는 바로 뒤 첫 단어로만 — 설명에 '영구 손실'이 섞여도 가격으로 읽는다
        self.team(ruling="약세 우세 — 가격: 적정가 ≈ 현재가, 영구 손실 위험은 작다는 데 양측 합의")
        c = rc.check(self.write("최종보고서.md", final_report()))
        self.assertFalse(c.failed, c.items)
        self.assertNotIn("⚠️", self.marks(c))
        self.team(ruling="약세 우세(영구 손실) — 경쟁 구도 붕괴")
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


class DecisionRulesTest(_Base):
    """판정 기준 3종(SKILL.md 7단계 규칙 8~10) — 작성일 RULE_DATE 이후 보고서는 ❌."""

    NEW_RUN = RUN_INFO.replace("2026-10-28", "2026-11-26").format(skill="investment-team")

    def ledger(self, rows=()):
        path = os.path.join(self.tmp.name, "ledger.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("id,기록일,종목,내재가치하단,내재가치상단\n")
            for r in rows:
                f.write(",".join(r) + "\n")
        return path

    def run_check(self, plan=PLAN, margin=MARGIN, extra="", ledger=None):
        self.team()
        self.debate(final_line=plan)
        path = self.write("최종보고서.md", final_report(run_info=self.NEW_RUN, plan=plan, margin=margin, extra=extra))
        return rc.check(path, ledger_path=self.ledger() if ledger is None else ledger)

    def fails(self, c):
        return " ".join(m for mark, m in c.items if mark == "❌")

    def test_new_report_passes_with_all_lines(self):
        c = self.run_check()
        self.assertFalse(c.failed, c.items)
        self.assertNotIn("⚠️", self.marks(c))

    def test_margin_line_rules(self):
        self.assertIn("**안전마진**", self.fails(self.run_check(margin="")))
        # 라벨 중앙과 다른 가치로 계산한 안전마진(판정에 쓴 가치 ≠ 라벨 범위)
        self.assertIn("라벨 범위는 판정에 실제로 쓴", self.fails(self.run_check(margin=MARGIN.replace("7.9%", "20%"))))
        # 공식과 다른 요구 안전마진, 라벨과 다른 U_v
        self.assertIn("공식 clip", self.fails(self.run_check(margin=MARGIN.replace("= 25%", "= 20%"))))
        self.assertIn("U_v 9 가 라벨", self.fails(self.run_check(margin=MARGIN.replace("U_v 5.3", "U_v 9"))))
        # 입력 근거 줄: 없음 / 하락률과 U_e 불일치 / 이자보상배율과 L 불일치
        self.assertIn("**이익 변동**", self.fails(self.run_check(margin=MARGIN.split("\n")[0])))
        self.assertIn("× 0.3 = U_e 12", self.fails(self.run_check(margin=MARGIN.replace("하락 50%", "하락 40%"))))
        self.assertIn("L 5 입니다", self.fails(self.run_check(margin=MARGIN.replace("20배", "5배"))))
        # 조정 이익이면 조정 근거 줄(허용 항목·출처) 필수
        adj = MARGIN.replace("영업이익 최대", "조정 영업이익(인수 무형자산 상각) 최대")
        self.assertIn("**조정 근거**", self.fails(self.run_check(margin=adj)))
        ok = adj + "\n**조정 근거**: 인수 무형자산 상각: 2016 +2.64B (출처: 10-K)"
        self.assertFalse(self.run_check(margin=ok).failed)
        # 금융업: 레버리지와 L 이 맞아야 한다
        fin = MARGIN.replace("이자보상배율 20배(2025) → L 0", "금융업 레버리지(총자산/자기자본) 13.5배(2025) → L 0")
        self.assertIn("레버리지 13.5배면 L 10", self.fails(self.run_check(margin=fin)))
        self.assertIn("레버리지(총자산/자기자본)가 없습니다", self.fails(self.run_check(
            margin=MARGIN.replace("이자보상배율 20배(2025) → L 0", "금융업 → L 0"))))
        no_hist = MARGIN.replace("영업이익 최대 하락 50% (2019→2020, 10개 해, DART)", "이력 부족(3개 해)")
        self.assertIn("U_e 는 30", self.fails(self.run_check(margin=no_hist)))
        # 약세 우세(가격)인데 안전마진이 요구 안전마진 이상 → 반려
        cheap = MARGIN.replace("기준가 175,000원", "기준가 140,000원").replace("7.9%", "26.3%")
        self.assertIn("가격이 문제라는 판정과 맞지 않습니다", self.fails(self.run_check(margin=cheap)))

    def test_old_report_only_warns(self):
        self.team()
        self.debate()
        c = rc.check(self.write("최종보고서.md", final_report(margin="")), ledger_path=self.ledger())
        self.assertFalse(c.failed, c.items)
        self.assertIn("**안전마진**", " ".join(m for mark, m in c.items if mark == "⚠️"))

    def test_value_change_rules(self):
        name = os.path.basename(self.tmp.name)
        led = self.ledger([("x", "2026-10-28", name, "200000", "240000")])
        self.assertIn("**가치 변경**", self.fails(self.run_check(ledger=led)))
        # 중앙 220,000 → 190,000 = -13.6%
        good = ("**가치 변경**: 이전 200,000~240,000원(2026-10-28) → 이번 180,000~200,000원 | "
                "**중앙 변화**: -13.6% = 데이터 -8.6% + 가정 -5%")
        c = self.run_check(ledger=led, extra=good)
        self.assertFalse(c.failed, c.items)
        self.assertIn("데이터 -8.6% + 가정 -5%", " ".join(m for _, m in c.items))
        self.assertIn("계산값 -13.6%", self.fails(self.run_check(ledger=led, extra=good.replace("-13.6% =", "-5% ="))))
        self.assertIn("원장(2026-10-28", self.fails(self.run_check(ledger=led, extra=good.replace("200,000~240", "210,000~240"))))
        big = good.replace("데이터 -8.6% + 가정 -5%", "데이터 -3.6% + 가정 −10%")
        self.assertIn("가정 변화 근거", self.fails(self.run_check(ledger=led, extra=big)))
        c = self.run_check(ledger=led, extra=big + "\n**가정 변화 근거**: 증설 사이클 진입(3Q CapEx +87%)\n")
        self.assertFalse(c.failed, c.items)
        # 같은 날 기록(이번 보고서 자신)은 이전 판단이 아니다
        same = self.ledger([("x", "2026-11-26", name, "200000", "240000")])
        self.assertFalse(self.run_check(ledger=same).failed)

    def test_uncertainty_rules(self):
        self.assertIn("불확실성 반영", self.fails(self.run_check(plan=PLAN.replace(" | **불확실성 반영**: 안전마진", ""))))
        # 안전마진 모드에 실적 확인 조건 → 이중 차감
        waiting = PLAN.replace("161,500원 1.5%", "161,500원 1.5%(4Q26 실적 확인 후)")
        self.assertIn("두 번 깎는", self.fails(self.run_check(plan=waiting)))
        # 반증 조건 미발생 확인은 상시 조건이라 허용
        ok = PLAN.replace("161,500원 1.5%", "161,500원 1.5%(반증 조건 미발생 확인 후)")
        self.assertFalse(self.run_check(plan=ok).failed)
        # 기준선 1차(161,500) 도달: 기준가 155,000 — 모든 차수를 현재가 아래로 내리면 반려
        reached = MARGIN.replace("기준가 175,000원", "기준가 155,000원").replace("7.9%", "18.4%")
        lowered = PLAN.replace("161,500원", "150,000원")
        self.assertIn("1차를 내린다", self.fails(self.run_check(plan=lowered, margin=reached)))
        self.assertFalse(self.run_check(margin=reached).failed)
        # 확인 대기: 1차를 기준선 아래로 내리면 반려, 이벤트 시점 필수
        wait = PLAN.replace("**현재 상태**: 대기", "**현재 상태**: 대기(4Q26 실적 확인 후 1차)").replace(
            "**불확실성 반영**: 안전마진", "**불확실성 반영**: 확인 대기")
        self.assertFalse(self.run_check(plan=wait).failed)
        self.assertIn("기준선(161,500.00) 아래로", self.fails(self.run_check(plan=wait.replace("161,500원", "150,000원"))))
        no_date = wait.replace("대기(4Q26 실적 확인 후 1차)", "대기(실적 확인 후)")
        self.assertIn("이벤트의 시점", self.fails(self.run_check(plan=no_date)))

    def test_formula_cross_check(self):
        old, rc.IV_RULE_DATE = rc.IV_RULE_DATE, "2026-11-26"           # 픽스처 작성일(2026-11-26)부터 시행으로
        self.addCleanup(setattr, rc, "IV_RULE_DATE", old)
        no_formula = MARGIN.replace("\n" + FORMULA, "")
        self.assertIn("**내재가치 산식**", self.fails(self.run_check(margin=no_formula)))
        # 공식 중앙 90,000 → 분석가 190,000 은 2.11배 → 괴리 근거 필수
        far = MARGIN.replace("범위 165,000~200,000", "범위 80,000~100,000")
        self.assertIn("공식 괴리 근거", self.fails(self.run_check(margin=far)))
        ok = far + "\n**공식 괴리 근거**: 공식은 10년 평균 마진, 분석가는 증설 후 구조적 마진 상향 가정"
        self.assertFalse(self.run_check(margin=ok).failed)
        manual = MARGIN.replace(FORMULA, "**내재가치 산식**: E 가정 의존형(명시 가정 DCF) | 자동 계산 불가(최근 5년 FCF ≤ 0)")
        self.assertIn("valuation-inputs.json", self.fails(self.run_check(margin=manual)))  # E 는 가정 입력 필수
        other = MARGIN.replace(FORMULA, "**내재가치 산식**: A 일반(2단계 오너어닝스 DCF) | 자동 계산 불가(주식수 미확보)")
        self.assertFalse(self.run_check(margin=other).failed)
        # D 유형: 입력 파일이 있어야 통과
        import json
        rel = os.path.relpath(self.write("valuation-inputs.json", json.dumps({"출처": ["사업보고서"], "유형": "D",
                                                                                 "유형사유": "지주"}, ensure_ascii=False)),
                              os.path.dirname(os.path.dirname(os.path.abspath(rc.__file__))))
        d_line = MARGIN.replace(FORMULA, FORMULA.replace("A 일반(2단계 오너어닝스 DCF)", "D 지주·복합(사업부별 합산)")
                                + f" | 입력: {rel}")
        self.assertFalse(self.run_check(margin=d_line).failed)
        self.assertIn("파일이 없습니다", self.fails(self.run_check(margin=d_line.replace(rel, "reports/없음/valuation-inputs.json"))))

    # --- investment-research · investment-checklist ---
    def solo(self, skill, label=LABEL, margin=MARGIN, extra="", ledger=None):
        run = RUN_INFO.replace("2026-10-28", "2026-11-26").format(skill=skill)
        text = final_report(skill=skill, label=label, run_info=run, plan="", margin=margin, extra=extra)
        return rc.check(self.write("r.md", text), ledger_path=self.ledger() if ledger is None else ledger)

    def test_research_hold_reason(self):
        self.assertIn("**관망 사유**", self.fails(self.solo("investment-research")))
        c = self.solo("investment-research", extra="**관망 사유**: 가격 — 안전마진 7.9% < 25%\n")
        self.assertFalse(c.failed, c.items)
        self.assertNotIn("⚠️", self.marks(c))
        self.assertNotIn("불확실성 반영", " ".join(m for _, m in c.items))   # 실행 계획 없는 스킬
        self.assertIn("**안전마진**", self.fails(self.solo("investment-research", margin="",
                                                         extra="**관망 사유**: 균형 — X\n")))
        # 가격 사유인데 안전마진 ≥ 요구 안전마진 → 반려, 확인 대기는 시점 필수
        cheap = MARGIN.replace("기준가 175,000원", "기준가 140,000원").replace("7.9%", "26.3%")
        self.assertIn("가격이 문제가 아닙니다", self.fails(self.solo(
            "investment-research", margin=cheap, extra="**관망 사유**: 가격 — 비싸다\n")))
        self.assertIn("이벤트의 시점", self.fails(self.solo(
            "investment-research", margin=cheap, extra="**관망 사유**: 확인 대기 — 실적 확인\n")))
        self.assertFalse(self.solo("investment-research", margin=cheap,
                                   extra="**관망 사유**: 확인 대기 — 4Q26 대손(2027-02)\n").failed)
        # 매수면 관망 사유 불필요
        self.assertFalse(self.solo("investment-research", label=LABEL.replace("관망", "매수")).failed)

    def test_research_value_change(self):
        name = os.path.basename(self.tmp.name)
        led = self.ledger([("x", "2026-10-28", name, "200000", "240000")])
        hold = "**관망 사유**: 가격 — X\n"
        self.assertIn("**가치 변경**", self.fails(self.solo("investment-research", extra=hold, ledger=led)))
        good = hold + ("**가치 변경**: 이전 200,000~240,000원(2026-10-28) → 이번 180,000~200,000원 | "
                       "**중앙 변화**: -13.6% = 데이터 -8.6% + 가정 -5%\n")
        self.assertFalse(self.solo("investment-research", extra=good, ledger=led).failed)

    def test_checklist_multi_company_rules_per_name(self):
        labels = ("**종목**: 텐센트 | " + LABEL + "\n\n**종목**: 알리바바 | " + LABEL.replace("관망", "회피")
                  + "\n\n**종목**: 바이두 | **판단**: 관망 | **확신도**: ★★ | **내재가치**: - | **반증 조건**: X")
        margin = "\n".join("**종목**: 텐센트 | " + x for x in MARGIN.split("\n"))
        reasons = "**종목**: 텐센트 | **관망 사유**: 가격 — X\n**종목**: 바이두 | **관망 사유**: 균형 — Y\n"
        c = self.solo("investment-checklist", label=labels, margin=margin, extra=reasons)
        self.assertFalse(c.failed, c.items)
        oks = " ".join(m for mark, m in c.items if mark == "✅")
        self.assertIn("(텐센트) 안전마진 7.9%", oks)
        self.assertIn("(바이두) 관망 사유: 균형", oks)        # 내재가치 '-' 는 안전마진 검사 생략
        # 종목 표시 없는 안전마진 줄은 복수 회사에서 인정하지 않는다
        c = self.solo("investment-checklist", label=labels, margin=MARGIN, extra=reasons)
        self.assertIn("(텐센트) 판정 근거에 `**안전마진**", self.fails(c))
        c = self.solo("investment-checklist", label=labels, margin=margin, extra=reasons.split("\n")[0])
        self.assertIn("(바이두) 관망인데", self.fails(c))


if __name__ == "__main__":
    unittest.main()
