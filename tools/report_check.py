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
                       `**관점 판단**: 매수|관망|회피` 줄 · 05-강세약세토론.md 의 네 발언 절(강세·약세 1·2라운드)과
                       두 최종 주장 줄, `**토론 판정**:` 줄, 토론 판정과 결론 판단의 대응
                       (강세 우세→매수 / 균형→관망 / 약세 우세(가격)→관망 / 약세 우세(영구 손실)→회피)
                       (이전 형식 05-교차반론.md 만 있으면 관점 판단 4개를 보고 ⚠️) · README.md
                       · `**실행 계획**` 줄(position_plan.py 형식)과 06-리스크토론-비중.md 의 마지막 실행 계획 줄 일치
                         (06 이 없으면 7.5단계 이전 보고서로 보고 ⚠️)
                       · 판정 기준 3종(작성일 2026-11-25 이후 ❌, 그 전 보고서는 ⚠️):
                         ① `**안전마진**: 기준가 P · 중앙 M → X% | **요구 안전마진**: 10 + max(U_v a, U_e b) + L c = M%`
                            와 `**이익 변동**: ... → U_e b% | **재무 위험**: ... → L c` (tools/mos_inputs.py calc 출력) —
                            X가 라벨 중앙으로 계산한 값과 같고(라벨 범위 = 판정에 쓴 가치), U_v 가 라벨 범위 폭과 같고,
                            M 이 공식과 같고, U_e·L 이 최대 하락률·이자보상배율과 맞고, 약세 우세(가격)인데 X ≥ M 이 아님
                         ② 원장에 같은 종목의 이전 판단이 있으면 `**가치 변경**: 이전 L~H(날짜) → 이번 L~H |
                            **중앙 변화**: A% = 데이터 B% + 가정 C%` 줄, |C| ≥ 10 이면 `**가정 변화 근거**:` 줄
                         ④ `**내재가치 산식**:` 줄(tools/intrinsic_value.py, 교차 검증 기준선) — 분석가 중앙이 공식 중앙과
                            ±50% 넘게 다르면 `**공식 괴리 근거**:` 줄 필수(작성일 2026-11-28 이후 ❌)
                         ③ 실행 계획 줄의 `**불확실성 반영**: 안전마진|확인 대기` — 안전마진이면 실적 확인 조건 금지,
                            기준선 1차가 이미 도달했으면 현재가에서 체결되는 차수가 있어야 함, 확인 대기면 1차를 기준선
                            아래로 내리지 않음(불확실성 이중 차감 금지)
  investment-research  '판정 근거' · '## 부록: 팩트시트'
  investment-checklist 라벨 줄(복수 회사면 **종목** 필드로 회사마다 하나)
  research·checklist   판정 기준 ①·② 는 team 과 같다(checklist 복수 회사는 줄 앞에 `**종목**: 회사명 |`, 회사마다).
                       ③ 대신 관망이면 `**관망 사유**: 가격|균형|확인 대기 — 설명` — 가격인데 안전마진 ≥ 요구 안전마진이면 반려,
                       확인 대기면 이벤트 시점 필수. 내재가치가 '-'(미산정)면 ①·② 는 건너뛴다

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
import mos_inputs as mi
import position_plan as pp

SKILLS = ("investment-team", "investment-research", "investment-checklist")
RUN_INFO_KEYS = ("작성일", "스킬", "데이터 시점", "데이터 출처·도구", "표본 검사")
TEAM_VIEWS = ("01-비즈니스모델분석-돤융핑관점.md", "02-재무밸류에이션분석-버핏관점.md",
              "03-산업경쟁분석-멍거관점.md", "04-리스크경영진평가-리루관점.md")
_VIEW_RE = re.compile(r"\*\*\s*관점 판단\s*\*\*\s*[:：]\s*(\S+)")
DEBATE_FILE = "05-강세약세토론.md"
LEGACY_REBUTTAL_FILE = "05-교차반론.md"
_DEBATE_TURNS = (("강세", 1), ("약세", 1), ("강세", 2), ("약세", 2))
_RULING_RE = re.compile(r"\*\*\s*토론 판정\s*\*\*\s*[:：]\s*(강세\s*우세|약세\s*우세|균형)(.*)")
_BASIS_RE = re.compile(r"\s*[(（]?\s*(?:[—–\-:：]\s*)?(가격|영구\s*손실)")
# 토론 판정 → 허용되는 결론 판단(SKILL.md 7단계 판정 규칙 7)
RULING_VERDICTS = {"강세 우세": ("매수",), "균형": ("관망",),
                   "약세 우세(가격)": ("관망",), "약세 우세(영구 손실)": ("회피",)}
# 판정 기준 3종(안전마진·가치 변경·불확실성 반영) 시행일. 이 날짜 전 보고서는 경고만 한다.
RULE_DATE = "2026-11-25"
UNCERTAINTY_MODES = ("안전마진", "확인 대기")
HOLD_REASONS = ("가격", "균형", "확인 대기")
# 내재가치 표준 산식 교차 검증(tools/intrinsic_value.py) 시행일과 괴리 한도
IV_RULE_DATE = "2026-11-28"
IV_GAP = 0.5
_PCT_RE = re.compile(r"([+\-]?\d+(?:\.\d+)?)\s*%")
_RANGE_RE = r"{}\s*([\d,]+(?:\.\d+)?)\s*[~∼]\s*([\d,]+(?:\.\d+)?)"
# 실적·이벤트 확인을 기다리는 조건. '반증 조건 미발생 확인'은 가격과 별개의 상시 조건이라 뺀 뒤 찾는다.
_CONFIRM_RE = re.compile(r"(실적|발표|가이던스|[1-4]Q|분기).{0,20}(확인|발표)|확인\s*(후|전)")
_FALSIFY_RE = re.compile(r"반증\s*조건[^,/|)]*")
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
    # 결과가 적혔다는 최소 증거: 판정어(통과·출고·반려)와 숫자. 자리표시 문구가 바뀌어도 걸리게 한다.
    has_result = re.search(r"\d", audit) and any(k in audit for k in ("통과", "출고", "반려"))
    if audit and (any(p in audit for p in _AUDIT_PENDING) or not has_result):
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
    check_debate(c, report_path, folder)
    check_plan(c, report_path, folder)
    (c.ok if os.path.exists(os.path.join(folder, "README.md")) else c.warn)(
        "README.md(프레임 개요)" + ("" if os.path.exists(os.path.join(folder, "README.md")) else " 가 없습니다."))


def parse_debate(path: str) -> dict:
    """05-강세약세토론.md → {"ruling": 판정 키 또는 None, "problems": 형식 문제 목록}.
    판정 키는 RULING_VERDICTS 의 키(약세 우세는 근거가 적혀 있을 때만 세분)."""
    with open(path, encoding="utf-8") as f:
        text = _norm(f.read())
    lines = [line for _, line in _outside_code(text)]
    problems = []
    for side, n in _DEBATE_TURNS:
        pat = re.compile(rf"^#{{2,4}}\s*{side}\s*{n}\s*라운드")
        if not any(pat.search(line.strip()) for line in lines):
            problems.append(f"`### {side} {n}라운드` 절이 없습니다")
    for side in ("강세", "약세"):
        pat = re.compile(rf"\*\*\s*{side} 최종 주장\s*\*\*\s*[:：]\s*\S")
        if not any(pat.search(line) for line in lines):
            problems.append(f"`**{side} 최종 주장**:` 줄이 없습니다")
    rulings = [m for m in (_RULING_RE.search(line) for line in lines) if m]
    ruling = None
    if not rulings:
        problems.append("`**토론 판정**: 강세 우세|약세 우세|균형 — ...` 줄이 없습니다")
    else:
        m = rulings[-1]
        head, rest = re.sub(r"\s+", " ", m.group(1)), m.group(2)
        if head == "약세 우세":
            # 근거는 '약세 우세' 바로 뒤 첫 단어로만 읽는다(`약세 우세 — 가격: ...` / `약세 우세(영구 손실) — ...`).
            # 설명 문장에 다른 쪽 단어가 섞여도("영구 손실 위험은 작다") 판독이 흔들리지 않게.
            b = _BASIS_RE.match(rest)
            ruling = f"약세 우세({'영구 손실' if b and b.group(1).startswith('영구') else '가격'})" if b else "약세 우세"
        else:
            ruling = head
    return {"ruling": ruling, "problems": problems}


def check_debate(c: Checker, report_path: str, folder: str):
    path = os.path.join(folder, DEBATE_FILE)
    if not os.path.exists(path):
        legacy = os.path.join(folder, LEGACY_REBUTTAL_FILE)
        if not os.path.exists(legacy):
            c.fail(f"강세·약세 토론 보고서가 없습니다: {DEBATE_FILE}")
            return
        views = _view_verdicts(legacy)
        bad = [v for v in views if v not in dl.VERDICTS]
        if len(views) < 4 or bad:
            c.fail(f"{LEGACY_REBUTTAL_FILE}: 관점 판단이 4개 필요(찾은 것 {len(views)}개" +
                   (f", 판독 불가 {bad}" if bad else "") + ").")
        else:
            c.warn(f"{LEGACY_REBUTTAL_FILE}: 이전 형식(교차 반론, 관점 판단 {', '.join(views)}). "
                   f"새 보고서는 {DEBATE_FILE}(강세·약세 토론)을 쓴다.")
        return
    d = parse_debate(path)
    for p in d["problems"]:
        c.fail(f"{DEBATE_FILE}: {p}")
    if not d["ruling"]:
        return
    if not d["problems"]:
        c.ok(f"{DEBATE_FILE}: 강세·약세 2라운드 · 최종 주장 2개 · 토론 판정 {d['ruling']}")
    with open(report_path, encoding="utf-8") as f:
        try:
            verdict = dl.parse_label(_norm(f.read()))["판단"]
        except (dl.ReportParseError, KeyError):
            return  # 라벨 줄 문제는 check_label 이 따로 잡는다
    if d["ruling"] == "약세 우세":
        allowed = ("관망", "회피")
        c.warn(f"{DEBATE_FILE}: 약세 우세의 근거(가격 / 영구 손실)를 판정 줄에 적으세요 — 관망과 회피를 가르는 기준입니다.")
    else:
        allowed = RULING_VERDICTS[d["ruling"]]
    if verdict in allowed:
        c.ok(f"토론 판정 {d['ruling']} ↔ 결론 판단 {verdict} 대응")
    else:
        c.fail(f"토론 판정 '{d['ruling']}' 인데 결론 판단이 '{verdict}' 입니다(허용: {'/'.join(allowed)}). "
               "판단을 고치거나, 판정이 틀렸다면 05의 판정 줄과 근거를 고치세요(SKILL.md 7단계 판정 규칙 7).")


def _plan_lines(text: str) -> list:
    return [line.strip() for _, line in _outside_code(text) if pp._PLAN_RE.search(line)]


def check_plan(c: Checker, report_path: str, folder: str):
    """최종보고서의 **실행 계획** 줄이 판독되고, 06 파일의 최종(마지막) 실행 계획 줄과 같은지."""
    with open(report_path, encoding="utf-8") as f:
        text = _norm(f.read())
    debate = os.path.join(folder, "06-리스크토론-비중.md")
    lines = _plan_lines(text)
    if not os.path.exists(debate):
        (c.warn if not lines else c.fail)(
            "06-리스크토론-비중.md 가 없습니다(7.5단계 리스크 토론 이전 형식)." if not lines else
            "최종보고서에 **실행 계획** 줄이 있는데 06-리스크토론-비중.md 가 없습니다.")
        return
    if not lines:
        c.fail("최종보고서에 `**실행 계획**:` 줄이 없습니다(7절, position_plan.py 형식).")
        return
    try:
        plan = pp.parse_plan(text)
    except dl.NoDataError as e:
        c.fail(f"최종보고서 실행 계획 줄: {e}")
        return
    with open(debate, encoding="utf-8") as f:
        d_lines = _plan_lines(_norm(f.read()))
    if not d_lines:
        c.fail("06-리스크토론-비중.md 에 Team Lead 결정 `**실행 계획**:` 줄이 없습니다.")
    elif d_lines[-1] != lines[0]:
        c.fail("최종보고서와 06-리스크토론-비중.md(마지막 줄)의 실행 계획이 다릅니다.")
    else:
        buys = ", ".join(f"{t['가격']:,.0f}@{t['비중']:g}%" for t in plan["분할매수"]) or "-"
        c.ok(f"실행 계획: 비중 상한 {plan['비중상한']:g}% · 분할 매수 {buys} (06 과 일치)")


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


def _num(x: str) -> float:
    return float(x.replace(",", ""))


def _fields(text: str, key: str, name: str = "") -> dict:
    """`**key**:` 가 있는 (코드 밖) 마지막 줄의 필드 사전. name 이 있으면 `**종목**: name` 이 붙은 줄만(복수 회사)."""
    out = {}
    pat = re.compile(rf"\*\*\s*{re.escape(key)}\s*\*\*\s*[:：]")
    for _, line in _outside_code(text):
        if pat.search(line):
            row = {k.strip(): v.strip() for k, v in dl._FIELD_RE.findall(line)}
            if not name or row.get("종목", "").strip("*").strip() == name:
                out = row
    return out


def _raw_line(text: str, key: str, name: str = "") -> str:
    """`**key**:` 가 있는 (코드 밖) 마지막 줄 전체(필드 밖의 `| ... |` 조각까지)."""
    out = ""
    pat = re.compile(rf"\*\*\s*{re.escape(key)}\s*\*\*\s*[:：]")
    for _, line in _outside_code(text):
        if pat.search(line):
            row = {k.strip(): v.strip() for k, v in dl._FIELD_RE.findall(line)}
            if not name or row.get("종목", "").strip("*").strip() == name:
                out = line
    return out


def _tag(name: str) -> str:
    return f"({name}) " if name else ""


def _signed(text: str) -> str:
    return text.replace("−", "-").replace("–", "-")


_REQ_RE = re.compile(r"U_v\s*([\d.]+).*?U_e\s*([\d.]+).*?L\s*([\d.]+).*?=\s*([\d.]+)\s*%")


def check_margin(c: Checker, text: str, folder: str, strict: bool, name: str = "", team: bool = True):
    """① 안전마진: 라벨 내재가치 중앙·기준가로 계산한 현재 안전마진, 종목별 요구 안전마진
    M = clip(10 + max(U_v, U_e) + L, 15, 45) 의 재계산, 입력(이익 변동·재무 위험) 근거, 판정과의 정합."""
    t = _tag(name)
    sev = lambda m: (c.fail if strict else c.warn)(t + m)  # noqa: E731
    pre = " 복수 회사는 줄 앞에 `**종목**: 회사명 |`." if name else ""
    try:
        label = dl.parse_label(text, name)
    except dl.ReportParseError:
        return None
    if label["판단"] == "회피" or not label["내재가치하단"]:
        return None
    f = _fields(text, "안전마진", name)
    if not f.get("안전마진") or not f.get("요구 안전마진"):
        sev("판정 근거에 `**안전마진**: 기준가 P · 중앙 M → X% | **요구 안전마진**: 10 + max(U_v a, U_e b) + L c = M%` "
            "줄이 없습니다(tools/mos_inputs.py calc 출력)." + pre)
        return None
    pm = re.search(r"기준가\s*([\d,]+(?:\.\d+)?)", f["안전마진"])
    xs = _PCT_RE.findall(_signed(f["안전마진"]))
    rq = _REQ_RE.search(f["요구 안전마진"])
    if not pm or not xs or not rq:
        sev(f"안전마진 줄을 읽을 수 없습니다: '{f['안전마진']} | {f['요구 안전마진']}'")
        return None
    price, x = _num(pm.group(1)), float(xs[-1])
    uv, ue, lp, m = (float(g) for g in rq.groups())
    lo, hi = float(label["내재가치하단"]), float(label["내재가치상단"])
    mid = (lo + hi) / 2
    calc = (1 - price / mid) * 100
    uv_calc = mi.u_v_from(lo, hi)
    ok = True
    if abs(x - calc) > 1.0:
        sev(f"안전마진 {x:g}% 가 라벨 내재가치 중앙({mid:,.2f})과 기준가로 계산한 {calc:.1f}% 와 다릅니다 — "
            "라벨 범위는 판정에 실제로 쓴 가치여야 합니다(규칙 8).")
        ok = False
    if abs(uv - uv_calc) > 0.2:
        sev(f"U_v {uv:g} 가 라벨 내재가치 범위로 계산한 {uv_calc:g} 와 다릅니다.")
        ok = False
    if lp not in (0, 5, 10) or not 0 <= ue <= mi.UE_CAP:
        sev(f"L 은 0/5/10, U_e 는 0~{mi.UE_CAP:g} 이어야 합니다(찾은 값 L {lp:g}, U_e {ue:g}).")
        ok = False
    m_calc = mi.required_mos(uv_calc, ue, lp)
    if abs(m - m_calc) > 0.2:
        sev(f"요구 안전마진 {m:g}% 가 공식 clip(10 + max(U_v, U_e) + L, 15, 45) = {m_calc:g}% 와 다릅니다.")
        ok = False
    ok &= _check_inputs(c, text, name, ue, lp, sev, pre)
    ruling = parse_debate(os.path.join(folder, DEBATE_FILE))["ruling"] if team and os.path.exists(
        os.path.join(folder, DEBATE_FILE)) else None
    if ruling == "약세 우세(가격)" and calc >= m_calc:
        sev(f"토론 판정이 '약세 우세 — 가격'인데 현재 안전마진 {calc:.1f}% 가 요구 안전마진 {m_calc:g}% 이상입니다 — "
            "가격이 문제라는 판정과 맞지 않습니다. 판정을 다시 하거나 라벨 범위를 판정에 쓴 가치로 고치세요.")
        ok = False
    if ok:
        c.ok(f"{t}안전마진 {calc:.1f}% (기준가 {price:,.2f} · 중앙 {mid:,.2f}) · 요구 {m_calc:g}% "
             f"(U_v {uv_calc:g}, U_e {ue:g}, L {lp:g})")
    return {"price": price, "margin": calc, "std": m_calc, "mid": mid, "verdict": label["판단"]}


def _check_inputs(c: Checker, text: str, name: str, ue: float, lp: float, sev, pre: str) -> bool:
    """`**이익 변동**: ... → U_e b% | **재무 위험**: ... → L c` 줄이 요구 안전마진의 U_e·L 과 맞는지."""
    f = _fields(text, "이익 변동", name)
    if not f.get("이익 변동") or not f.get("재무 위험"):
        sev("`**이익 변동**: ... → U_e b% | **재무 위험**: ... → L c` 줄이 없습니다(tools/mos_inputs.py calc 출력, "
            "재무 원본으로 계산한 근거)." + pre)
        return False
    ok = True
    ev, lv = _signed(f["이익 변동"]), f["재무 위험"]
    got_ue = re.search(r"U_e\s*([\d.]+)", ev)
    got_l = re.search(r"L\s*([\d.]+)", lv)
    if not got_ue or abs(float(got_ue.group(1)) - ue) > 0.05:
        sev(f"이익 변동 줄의 U_e 가 요구 안전마진의 U_e {ue:g} 와 다릅니다: '{f['이익 변동']}'")
        ok = False
    dd = re.search(r"최대\s*하락\s*([\d.]+)\s*%", ev)
    if dd and "직접" not in ev:
        want = round(min(mi.UE_FACTOR * float(dd.group(1)), mi.UE_CAP), 1)
        if abs(want - ue) > 0.1:
            sev(f"최대 하락 {dd.group(1)}% × {mi.UE_FACTOR:g} = U_e {want:g} 인데 {ue:g} 를 썼습니다.")
            ok = False
    elif not dd and "직접" not in ev and abs(ue - mi.UE_CAP) > 0.05:
        sev(f"이익 변동 줄에 최대 하락률이 없으면(이력 부족·데이터 미확보) U_e 는 {mi.UE_CAP:g} 입니다.")
        ok = False
    if "조정" in ev.split("최대")[0]:
        adj = _fields(text, "조정 근거", name).get("조정 근거", "")
        items = [i for i in mi.ADDBACK_ITEMS if i in adj]
        if not adj or not items or "출처" not in adj:
            sev("조정 이익을 썼는데 `**조정 근거**: 항목: 연도별 금액 (출처: ...)` 줄이 없거나 허용 항목·출처가 없습니다 "
                f"(허용: {', '.join(mi.ADDBACK_ITEMS)}).")
            ok = False
    if not got_l or abs(float(got_l.group(1)) - lp) > 0.05:
        sev(f"재무 위험 줄의 L 이 요구 안전마진의 L {lp:g} 와 다릅니다: '{f['재무 위험']}'")
        ok = False
    lev = re.search(r"레버리지[^\d]*?([\d.]+)\s*배", lv)
    if lev:
        _, want_l = mi.financial_penalty(float(lev.group(1)), 1.0)
        if want_l != lp:
            sev(f"금융업 레버리지 {lev.group(1)}배면 L {want_l:g} 입니다(5배 미만 0, 5~10배 5, 10배 이상 10).")
            ok = False
    elif "금융업" in lv and "산정 불가" not in lv and "직접" not in lv:
        sev("금융업 재무 위험 줄에 레버리지(총자산/자기자본)가 없습니다 — mos_inputs.py calc 출력을 옮기세요.")
        ok = False
    cov = re.search(r"이자보상배율\s*(-?[\d.]+)\s*배", lv)
    if cov:
        _, want_l = mi.leverage_penalty(float(cov.group(1)), 1.0, False)
        if want_l != lp:
            sev(f"이자보상배율 {cov.group(1)}배면 L {want_l:g} 입니다(8배 이상 0, 3~8배 5, 3배 미만 10).")
            ok = False
    return ok


def check_value_change(c: Checker, text: str, folder: str, run_date: str, strict: bool, ledger_path: str,
                       name: str = ""):
    """② 같은 종목의 이전 판단이 원장에 있으면 내재가치 변경을 데이터 변화·가정 변화로 나눴는지.
    종목은 복수 회사 보고서면 **종목** 값, 아니면 보고서 폴더 이름(reports/{회사명}/)."""
    t = _tag(name)
    sev = lambda m: (c.fail if strict else c.warn)(t + m)  # noqa: E731
    if not ledger_path or not os.path.exists(ledger_path) or not run_date:
        return
    try:
        label = dl.parse_label(text, name)
    except dl.ReportParseError:
        return
    if not label["내재가치하단"]:
        return
    company = name or os.path.basename(folder)
    prior = sorted((r for r in dl._read(ledger_path)
                    if r.get("종목") == company and r.get("기록일", "") < run_date
                    and r.get("내재가치하단") and r.get("내재가치상단")), key=lambda r: r["기록일"])
    if not prior:
        c.ok(f"{t}가치 변경 분해: 원장에 이전 판단 없음(첫 리서치)")
        return
    last = prior[-1]
    o_lo, o_hi = float(last["내재가치하단"]), float(last["내재가치상단"])
    n_lo, n_hi = float(label["내재가치하단"]), float(label["내재가치상단"])
    f = _fields(text, "가치 변경", name)
    if not f.get("가치 변경") or not f.get("중앙 변화"):
        sev(f"원장에 이전 판단({last['기록일']}, 내재가치 {o_lo:,.2f}~{o_hi:,.2f})이 있는데 `**가치 변경**: 이전 L~H(날짜) → "
            "이번 L~H | **중앙 변화**: A% = 데이터 B% + 가정 C%` 줄이 없습니다(규칙 9).")
        return
    before = re.search(_RANGE_RE.format("이전"), f["가치 변경"])
    after = re.search(_RANGE_RE.format("이번"), f["가치 변경"])
    pcts = [float(p) for p in _PCT_RE.findall(_signed(f["중앙 변화"]))]
    if not before or not after or len(pcts) < 3:
        sev(f"가치 변경 줄을 읽을 수 없습니다: '{f['가치 변경']} | {f['중앙 변화']}'")
        return
    close = lambda a, b: abs(a - b) <= max(abs(b) * 0.005, 0.01)  # noqa: E731
    ok = True
    if not (close(_num(before.group(1)), o_lo) and close(_num(before.group(2)), o_hi)):
        sev(f"가치 변경의 이전 범위가 원장({last['기록일']}: {o_lo:,.2f}~{o_hi:,.2f})과 다릅니다.")
        ok = False
    if not (close(_num(after.group(1)), n_lo) and close(_num(after.group(2)), n_hi)):
        sev(f"가치 변경의 이번 범위가 라벨 줄({n_lo:,.2f}~{n_hi:,.2f})과 다릅니다.")
        ok = False
    a, b, cc = pcts[0], pcts[1], pcts[2]
    calc = ((n_lo + n_hi) / (o_lo + o_hi) - 1) * 100
    if abs(a - calc) > 1.0:
        sev(f"중앙 변화 {a:+g}% 가 계산값 {calc:+.1f}% 와 다릅니다.")
        ok = False
    if abs(b + cc - a) > 1.0:
        sev(f"데이터 {b:+g}% + 가정 {cc:+g}% 가 중앙 변화 {a:+g}% 와 맞지 않습니다.")
        ok = False
    if abs(cc) >= 10 and not _fields(text, "가정 변화 근거", name).get("가정 변화 근거"):
        sev(f"가정 변화만으로 중앙이 {cc:+g}% 움직였는데 `**가정 변화 근거**:` 줄이 없습니다(±10% 이상은 근거 필수).")
        ok = False
    if ok:
        c.ok(f"{t}가치 변경 분해: 중앙 {a:+g}% = 데이터 {b:+g}% + 가정 {cc:+g}% (이전 {last['기록일']})")


def check_uncertainty(c: Checker, text: str, margin, strict: bool):
    """③ 불확실성은 안전마진 또는 확인 대기 중 하나로만 반영한다(이중 차감 금지)."""
    sev = c.fail if strict else c.warn
    if not margin or margin["verdict"] == "회피":
        return
    try:
        plan = pp.parse_plan(text)
    except dl.NoDataError:
        return  # 실행 계획 줄 문제는 check_plan 이 잡는다
    mode = plan.get("불확실성반영", "")
    if mode not in UNCERTAINTY_MODES:
        sev(f"실행 계획 줄에 `**불확실성 반영**: 안전마진|확인 대기` 가 없습니다(찾은 값: '{mode or '-'}', 규칙 10).")
        return
    conds = " ".join([t["조건"] for t in plan["분할매수"]] + [plan["현재상태"]])
    waiting = bool(_CONFIRM_RE.search(_FALSIFY_RE.sub("", conds)))
    first = pp.round_price(margin["mid"] * (1 - (margin["std"] - 10) / 100))
    top = max((t["가격"] for t in plan["분할매수"]), default=0)
    reached = margin["price"] <= first
    ok = True
    if mode == "안전마진":
        if waiting:
            sev("불확실성 반영이 '안전마진'인데 실적·이벤트 확인 조건이 붙어 있습니다 — 같은 불확실성을 두 번 깎는 것입니다. "
                "확인을 기다리려면 '확인 대기'로 바꾸고 1차를 기준선 가격에 두세요.")
            ok = False
        if reached and top < margin["price"] * 0.99:
            sev(f"기준선 1차({first:,.2f})가 이미 도달했는데(기준가 {margin['price']:,.2f}) 모든 차수를 현재가 아래로 내렸습니다 — "
                "'관망이라 1차를 내린다'는 금지입니다(규칙 10).")
            ok = False
    else:
        if top < first * 0.99:
            sev(f"불확실성 반영이 '확인 대기'면 1차를 기준선({first:,.2f}) 아래로 내리지 않습니다(찾은 1차 {top:,.2f}).")
            ok = False
        if not re.search(r"\d", plan["현재상태"]):
            sev("확인 대기인데 현재 상태에 기다리는 이벤트의 시점(예: 4Q26, 2027-02)이 없습니다.")
            ok = False
    if ok:
        c.ok(f"불확실성 반영: {mode}" + (f" · 기준선 1차 {first:,.2f} 도달" if reached else ""))


def check_formula(c: Checker, text: str, name: str, run_date: str):
    """④ 내재가치 표준 산식 교차 검증: `**내재가치 산식**:` 줄(intrinsic_value.py 출력)이 있고,
    분석가 범위 중앙이 공식 범위 중앙과 ±50% 넘게 다르면 `**공식 괴리 근거**:` 줄이 있다."""
    t = _tag(name)
    sev = lambda m: (c.fail if run_date >= IV_RULE_DATE else c.warn)(t + m)  # noqa: E731
    try:
        label = dl.parse_label(text, name)
    except dl.ReportParseError:
        return
    if not label["내재가치하단"]:
        return
    f = _fields(text, "내재가치 산식", name)
    line = f.get("내재가치 산식", "")
    if not line:
        sev("`**내재가치 산식**:` 줄이 없습니다 — `python3 tools/intrinsic_value.py calc {종목코드} --as-of {데이터 시점} "
            "--trade-currency {거래 통화}` 출력을 판정 근거에 옮기세요(교차 검증 기준선).")
        return
    whole = _raw_line(text, "내재가치 산식", name)
    if re.search(r"D 지주|E 가정|입력:", whole):
        mp = re.search(r"입력:\s*(\S+\.json)", whole)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, mp.group(1)) if mp else ""
        if not mp or not os.path.exists(path):
            sev("D·E 유형 또는 수기 입력을 쓴 산식인데 `입력: reports/{회사명}/valuation-inputs.json` 경로가 없거나 파일이 없습니다.")
            return
        try:
            import intrinsic_value as iv
            iv.load_inputs(path)
        except SystemExit as e:
            sev(f"수기 입력 파일 검사 실패: {e}")
            return
    if "자동 계산 불가" in whole:
        if re.search(r"D 지주|E 가정", whole):
            sev("D·E 유형은 자동 계산 불가로 둘 수 없습니다 — valuation-inputs.json 에 가정(D 구성·E 매출 경로·목표 마진)을 넣고 다시 계산하세요.")
            return
        c.ok(f"{t}내재가치 산식: 자동 계산 불가(사유 기재)")
        return
    m = re.search(_RANGE_RE.format("범위"), whole)
    if not m:
        sev(f"내재가치 산식 줄에서 `범위 L~H` 를 읽을 수 없습니다: '{whole[:120]}'")
        return
    flo, fhi = _num(m.group(1)), _num(m.group(2))
    fmid = (flo + fhi) / 2
    amid = (float(label["내재가치하단"]) + float(label["내재가치상단"])) / 2
    if fmid <= 0:
        c.ok(f"{t}내재가치 산식: 공식 중앙 ≤ 0(비교 생략)")
        return
    ratio = amid / fmid
    if abs(ratio - 1) > IV_GAP and not _fields(text, "공식 괴리 근거", name).get("공식 괴리 근거"):
        sev(f"분석가 중앙 {amid:,.2f} 가 공식 중앙 {fmid:,.2f} 의 {ratio:.2f}배(±{IV_GAP:.0%} 초과)인데 "
            "`**공식 괴리 근거**:` 줄이 없습니다 — 어느 가정(성장·할인율·정상 마진·시장 할인)이 다른지 쓰세요.")
        return
    c.ok(f"{t}내재가치 산식: 공식 중앙 {fmid:,.2f} · 분석가/공식 {ratio:.2f}배")


def check_decision_rules(c: Checker, text: str, path: str, skill: str, ledger_path: str):
    """판정 기준 3종(안전마진·가치 변경·불확실성 반영). 복수 회사(checklist)는 **종목** 마다."""
    run_date = dl.parse_run_info(text).get("작성일", "")
    strict = run_date >= RULE_DATE
    folder = os.path.dirname(os.path.abspath(path))
    names = sorted({r["종목"] for r in dl._label_lines(text) if r.get("종목")}) or [""]
    team = skill == "investment-team"
    for name in names:
        margin = check_margin(c, text, folder, strict, name, team)
        check_value_change(c, text, folder, run_date, strict, ledger_path, name)
        check_formula(c, text, name, run_date)
        if team:
            check_uncertainty(c, text, margin, strict)
        else:
            check_hold_reason(c, text, margin, strict, name)


def check_hold_reason(c: Checker, text: str, margin, strict: bool, name: str = ""):
    """③' research·checklist: 관망이면 사유(가격 / 균형 / 확인 대기)를 하나 고른다.
    가격인데 안전마진이 요구 안전마진 이상이면 반려(규칙 8), 확인 대기면 이벤트 시점 필수(규칙 10)."""
    t = _tag(name)
    sev = lambda m: (c.fail if strict else c.warn)(t + m)  # noqa: E731
    try:
        verdict = dl.parse_label(text, name)["판단"]
    except dl.ReportParseError:
        return
    if verdict != "관망":
        return
    f = _fields(text, "관망 사유", name)
    value = f.get("관망 사유", "")
    reason = next((r for r in HOLD_REASONS if value.startswith(r)), "")
    if not reason:
        sev(f"관망인데 `**관망 사유**: 가격|균형|확인 대기 — 설명` 줄이 없거나 사유를 읽을 수 없습니다(찾은 값: '{value or '-'}')."
            + (" 복수 회사는 줄 앞에 `**종목**: 회사명 |`." if name else ""))
        return
    ok = True
    if reason == "가격" and margin and margin["margin"] >= margin["std"]:
        sev(f"관망 사유가 '가격'인데 현재 안전마진 {margin['margin']:.1f}% 가 요구 안전마진 {margin['std']:g}% 이상입니다 — "
            "가격이 문제가 아닙니다. 판단을 다시 하거나 라벨 범위를 판정에 쓴 가치로 고치세요(규칙 8).")
        ok = False
    if reason == "확인 대기" and not re.search(r"\d", value):
        sev("관망 사유가 '확인 대기'인데 기다리는 이벤트의 시점(예: 4Q26 실적, 2027-02)이 없습니다(규칙 10).")
        ok = False
    if ok:
        c.ok(f"{t}관망 사유: {reason}")


def check(path: str, skill: str = "", ledger_path=None) -> Checker:
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
    if skill in SKILLS:
        check_decision_rules(c, text, path, skill, dl.LEDGER if ledger_path is None else ledger_path)
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
