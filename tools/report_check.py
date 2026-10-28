#!/usr/bin/env python3
"""보고서 형식 검사 — 출고 전에 판단 원장·회고가 읽어야 할 고정 형식이 다 있는지 확인한다. stdlib만.

report_audit.py 가 '숫자가 맞는가'를 표본으로 본다면, 이 도구는 '형식이 맞는가'를 전수로 본다.
라벨 줄이 깨지면 decision_ledger.py add --from-report 가 기록을 거부하고, 실행 정보가 빠지면 나중에
판단이 틀렸을 때 원인(데이터 시점·출처)을 추적할 수 없다. 사람이 눈으로 보던 것을 기계로 확인한다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)의 구조화 출력 검증
  (Pydantic 스키마 + 실패 시 원문 폴백) — 여기서는 마크다운 고정 줄을 스키마로 본다.

검사 항목(❌ 하나라도 있으면 반려, ⚠️는 출고 가능하지만 고칠 것):
  공통      결론 라벨 줄 판독(decision_ledger 와 같은 파서) · '## 실행 정보' 절이 맨 끝에 있고
            작성일·스킬·데이터 시점·데이터 출처·표본 검사 줄이 있음 · 표본 검사 결과가 실제로 적힘
            ⚠️ 반 별/빈 별(☆, ½) · ⚠️ 주관 표현("내 생각에는", "느낌상", "명백히")
  investment-team      '판정 근거' 절 · '## 부록: 팩트시트' 절 · 같은 폴더의 01~04 관점 보고서 각각의
                       `**관점 판단**: 매수|관망|회피` 줄 · 05-교차반론.md 의 관점 판단 4개 · README.md
  investment-research  '판정 근거' · '## 부록: 팩트시트'
  investment-checklist 라벨 줄(복수 회사면 **종목** 필드로 회사마다 하나)

사용법:
    python3 tools/report_check.py reports/삼성전자/최종보고서.md            # 스킬은 실행 정보에서 읽음
    python3 tools/report_check.py reports/다중회사비교-checklist-20260408.md --skill investment-checklist

종료 코드: 0 출고 가능(⚠️ 포함) / 1 반려(❌ 있음) / 3 파일 없음
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import os
import re
import sys
import unicodedata

from _us_common import EXIT_NO_DATA
import decision_ledger as dl

SKILLS = ("investment-team", "investment-research", "investment-checklist")
RUN_INFO_KEYS = ("작성일", "스킬", "데이터 시점", "데이터 출처·도구", "표본 검사")
TEAM_VIEWS = ("01-비즈니스모델분석-돤융핑관점.md", "02-재무밸류에이션분석-버핏관점.md",
              "03-산업경쟁분석-멍거관점.md", "04-리스크경영진평가-리루관점.md")
_VIEW_RE = re.compile(r"\*\*\s*관점 판단\s*\*\*\s*[:：]\s*(\S+)")
_SUBJECTIVE = ("내 생각에는", "제 생각에는", "느낌상", "명백히")
# 표본 검사 줄에 결과 대신 예정만 적힌 경우(작성 중 자리표시)
_AUDIT_PENDING = ("출고 절차에서 기록", "예정", "미실시", "TODO", "{")


class Checker:
    def __init__(self):
        self.items = []

    def ok(self, msg):
        self.items.append(("✅", msg))

    def fail(self, msg):
        self.items.append(("❌", msg))

    def warn(self, msg):
        self.items.append(("⚠️", msg))

    @property
    def failed(self):
        return any(m == "❌" for m, _ in self.items)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _outside_code(text: str):
    """코드 블록 밖의 (줄 번호, 줄). 코드 블록 안은 예시라서 검사하지 않는다."""
    fenced = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield i, line


def _headings(text: str) -> list:
    return [(i, line) for i, line in _outside_code(text) if re.match(r"#{1,6}\s", line)]


def check_label(c: Checker, text: str, skill: str):
    rows = dl._label_lines(text)
    names = [r["종목"] for r in rows if r.get("종목")]
    targets = sorted(set(names)) if names else [""]
    if skill == "investment-checklist" and names and len(names) != len(set(names)):
        c.fail(f"라벨 줄의 **종목** 이 중복됩니다: {sorted(n for n in set(names) if names.count(n) > 1)}")
    for name in targets:
        try:
            got = dl.parse_label(text, name)
        except dl.ReportParseError as e:
            c.fail(f"결론 라벨 줄{f'({name})' if name else ''}: {e}")
            continue
        iv = f"{got['내재가치하단']}~{got['내재가치상단']}" if got["내재가치하단"] else "-"
        c.ok(f"결론 라벨 줄{f'({name})' if name else ''}: {got['판단']} ★{got['확신도']} · 내재가치 {iv}")
        if not got["반증조건"]:
            c.warn(f"결론 라벨 줄{f'({name})' if name else ''}에 반증 조건이 없습니다(회고 때 논지 판정 기준).")


def check_run_info(c: Checker, text: str, skill_arg: str) -> str:
    heads = _headings(text)
    idx = [k for k, (_, h) in enumerate(heads) if "실행 정보" in h and h.startswith("## ")]
    if not idx:
        c.fail("'## 실행 정보' 절이 없습니다(형식: .claude/skills/decision-ledger/SKILL.md 1-1b).")
        return skill_arg
    if idx[-1] != len(heads) - 1:
        c.fail(f"'## 실행 정보' 뒤에 다른 절이 있습니다({heads[idx[-1] + 1][1].strip()}) — 실행 정보는 맨 끝.")
    info = dl.parse_run_info(text)
    missing = [k for k in RUN_INFO_KEYS if not info.get(k)]
    if missing:
        c.fail(f"실행 정보에 빠진 줄: {', '.join(missing)}")
    else:
        c.ok("실행 정보: " + ", ".join(RUN_INFO_KEYS))
    if info.get("작성일") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", info["작성일"]):
        c.fail(f"실행 정보 작성일 '{info['작성일']}' 은 YYYY-MM-DD 형식이 아닙니다.")
    audit = info.get("표본 검사", "")
    if audit and any(p in audit for p in _AUDIT_PENDING):
        c.fail(f"표본 검사 결과가 아직 없습니다('{audit}') — report_audit.py verdict 결과를 적을 것.")
    skill = info.get("스킬", "")
    if skill_arg and skill and skill != skill_arg:
        c.fail(f"실행 정보 스킬 '{skill}' 과 --skill '{skill_arg}' 이 다릅니다.")
    return skill_arg or skill


def check_style(c: Checker, text: str):
    half = [i for i, line in _outside_code(text) if re.search(r"★☆|½", line)]
    if half:
        c.warn(f"반 별·빈 별 표기(☆, ½) — ★1~5 정수만 쓴다(CLAUDE.md): {_lines(half)}")
    for phrase in _SUBJECTIVE:
        hits = [i for i, line in _outside_code(text) if phrase in line]
        if hits:
            c.warn(f"주관 표현 '{phrase}' — '데이터에 따르면' 등으로 바꿀 것: {_lines(hits)}")


def _lines(nums: list) -> str:
    shown = ", ".join(str(n) for n in nums[:8])
    return f"{shown}줄" + (f" 외 {len(nums) - 8}곳" if len(nums) > 8 else "")


def _has_heading(text: str, word: str, prefix: str = "") -> bool:
    return any(word in h and h.startswith(prefix) for _, h in _headings(text))


def check_skill_sections(c: Checker, text: str, skill: str):
    if skill in ("investment-team", "investment-research"):
        # research 는 판정 근거를 종합 메모 안에 쓰므로 제목이 아니어도 된다.
        found = _has_heading(text, "판정 근거") or (skill == "investment-research" and "판정 근거" in text)
        (c.ok if found else c.fail)("'판정 근거' 절" + ("" if found else "이 없습니다(결정한 논거·가장 강한 반대 논거·판단을 바꿀 조건)."))
        found = _has_heading(text, "부록: 팩트시트", "## ")
        (c.ok if found else c.fail)("'## 부록: 팩트시트' 절" + ("" if found else "이 없습니다(fact_sheet.py 출력 전체)."))


def check_team_dir(c: Checker, report_path: str):
    folder = os.path.dirname(os.path.abspath(report_path))
    for name in TEAM_VIEWS:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            c.fail(f"관점 보고서가 없습니다: {name}")
            continue
        views = _view_verdicts(path)
        if not views:
            c.fail(f"{name}: `**관점 판단**: 매수|관망|회피` 줄이 없습니다.")
        elif views[-1] not in dl.VERDICTS:
            c.fail(f"{name}: 관점 판단 '{views[-1]}' 은 매수/관망/회피가 아닙니다.")
        else:
            c.ok(f"{name}: 관점 판단 {views[-1]}")
    path = os.path.join(folder, "05-교차반론.md")
    if not os.path.exists(path):
        c.fail("교차 반론 보고서가 없습니다: 05-교차반론.md")
    else:
        views = _view_verdicts(path)
        bad = [v for v in views if v not in dl.VERDICTS]
        if len(views) < 4 or bad:
            c.fail(f"05-교차반론.md: 관점 판단이 4개 필요(찾은 것 {len(views)}개" +
                   (f", 판독 불가 {bad}" if bad else "") + ").")
        else:
            c.ok(f"05-교차반론.md: 관점 판단 {len(views)}개 ({', '.join(views)})")
    (c.ok if os.path.exists(os.path.join(folder, "README.md")) else c.warn)(
        "README.md(프레임 개요)" + ("" if os.path.exists(os.path.join(folder, "README.md")) else " 가 없습니다."))


def _view_verdicts(path: str) -> list:
    """`**관점 판단**: 관망 — ...` / `**관점 판단**: 관망 유지 — ...` → ['관망', ...]."""
    with open(path, encoding="utf-8") as f:
        text = _norm(f.read())
    out = []
    for _, line in _outside_code(text):
        m = _VIEW_RE.search(line)
        if m:
            out.append(m.group(1).strip("*,.—-"))
    return out


def check(path: str, skill: str = "") -> Checker:
    with open(path, encoding="utf-8") as f:
        text = _norm(f.read())
    c = Checker()
    skill = check_run_info(c, text, skill)
    if skill and skill not in SKILLS:
        c.warn(f"스킬 '{skill}' 은 형식 규칙이 정해진 스킬({', '.join(SKILLS)})이 아니라 공통 항목만 검사합니다.")
    check_label(c, text, skill)
    check_skill_sections(c, text, skill)
    if skill == "investment-team":
        check_team_dir(c, path)
    check_style(c, text)
    return c


def main():
    p = argparse.ArgumentParser(description="보고서 형식 검사(출고 전).")
    p.add_argument("report", help="보고서 경로")
    p.add_argument("--skill", default="", choices=("",) + SKILLS, help="기본: 실행 정보의 스킬 줄")
    a = p.parse_args()
    if not os.path.exists(a.report):
        print(f"NO_DATA: 파일이 없습니다: {a.report}")
        sys.exit(EXIT_NO_DATA)
    c = check(a.report, a.skill)
    fails = sum(1 for m, _ in c.items if m == "❌")
    warns = sum(1 for m, _ in c.items if m == "⚠️")
    print(f"{'FAIL' if c.failed else 'PASS'}: {a.report} — ❌ {fails} / ⚠️ {warns}")
    for mark, msg in c.items:
        print(f"  {mark} {msg}")
    if c.failed:
        print("반려: ❌ 항목을 고친 뒤 다시 검사한다(라벨 줄은 손으로 원장에 채우지 말고 보고서를 고친다).")
    sys.exit(1 if c.failed else 0)


if __name__ == "__main__":
    main()
