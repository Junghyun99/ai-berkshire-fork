#!/usr/bin/env python3
"""리서치 실행 상태 — 긴 멀티 Agent 실행이 중간에 끊겨도 끝난 단계는 건너뛰고 이어서 실행한다. stdlib만.

investment-team 한 번은 Agent 4개 + 교차 반론 + 리스크 토론 + 검사·기록까지 수십 분이 걸린다. 그 사이 Agent 하나가
API 오류로 죽거나(실제 사례: 2026-10-28 삼성전자 실행에서 멍거 관점 Agent가 보고서 저장 도중 중단) 세션이 끊기면,
지금까지는 무엇이 끝났는지 사람이 파일을 열어 보고 판단했다. 이 도구는 단계마다 '끝남'을 기록하고, 다시 시작할 때
다음에 할 단계만 알려 준다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)의 LangGraph 체크포인트
  (종목·날짜별 thread, 끝난 노드는 건너뛰고 재개, 성공하면 체크포인트 삭제)를 파일 기반 스킬 실행에 맞게 변형.

원칙:
  - '끝남'은 선언이 아니라 검증이다. done 은 그 단계 산출물을 검사해 통과할 때만 기록한다
    (예: 관점 보고서에 `**관점 판단**` 줄이 없으면 — 저장 도중 끊긴 파일이면 — 끝난 것으로 치지 않는다).
  - 같은 기준값으로 재개한다. 팩트시트·교훈·실행 계획 기준선 같은 입력은 put 으로 상태에 넣어 두고, 재개한 실행은
    다시 뽑지 않고 get 으로 같은 값을 쓴다(중간에 주가가 바뀌어 관점마다 기준이 달라지는 것을 막는다).
  - 앞 단계를 다시 하면 그 뒤에 끝났던 단계는 '대기'로 되돌린다(예: 관점 보고서를 다시 쓰면 교차 반론도 다시).
  - 같은 단계가 2번 실패하면 폴백(Team Lead 대리 작성)을 권한다. 대리 작성은 산출물에 그 사실을 밝힌다.
  - 모든 단계가 끝나면 finish 가 상태 파일을 지운다(체크포인트는 성공하면 남기지 않는다).

상태 파일: reports/{회사명}/.run-state-{스킬}.json  (중간 산출물. 중단돼 세션을 넘겨야 할 때만 작업 브랜치에 커밋하고,
           finish 로 지운 뒤 최종 커밋에는 남기지 않는다)

사용법:
    python3 tools/run_state.py start  --company 삼성전자 --ticker 005930            # 새 실행(이미 진행 중이면 거부)
    python3 tools/run_state.py status --company 삼성전자                             # 단계별 상태와 다음 단계
    python3 tools/run_state.py put    --company 삼성전자 --key factsheet --file /tmp/fs.md
    python3 tools/run_state.py get    --company 삼성전자 --key factsheet
    python3 tools/run_state.py done   --company 삼성전자 --step view-buffett        # 산출물 검증 후 기록
    python3 tools/run_state.py fail   --company 삼성전자 --step view-munger --error "API 오류로 중단"
    python3 tools/run_state.py next   --company 삼성전자                             # 다음 단계 id 한 줄
    python3 tools/run_state.py finish --company 삼성전자                             # 전부 끝났으면 상태 삭제

종료 코드: 0 정상 / 1 검증 실패·진행 중 충돌 / 3 상태 없음
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime

from _us_common import NoDataError, run
import decision_ledger as dl
import report_check as rc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.environ.get("RUN_STATE_REPORTS_DIR") or os.path.join(_ROOT, "reports")
MAX_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# 단계 정의: (id, 설명, 산출물 경로(회사 폴더 기준, 없으면 None), 검증 종류, 묶음)
#   묶음이 같은 단계는 병렬로 해도 된다(관점 보고서 4개). 어떤 단계를 다시 끝내면 더 뒤 묶음의 단계만 되돌린다.
# ---------------------------------------------------------------------------

_TEAM_VIEWS = dict(zip(("view-duan", "view-buffett", "view-munger", "view-lilu"), rc.TEAM_VIEWS))

SKILL_STEPS = {
    "investment-team": [
        ("context", "1단계 과거 판단·교훈 확인(show/lessons 결과를 put)", None, "has_blob:lessons", 0),
        ("factsheet", "1.6단계 팩트시트(put --key factsheet)", None, "has_blob:factsheet", 0),
        *[(k, f"4단계 관점 보고서 {v}", v, "view", 1) for k, v in _TEAM_VIEWS.items()],
        ("rebuttal", "5.5단계 교차 반론 05-교차반론.md", "05-교차반론.md", "rebuttal", 2),
        ("final", "7단계 최종보고서 결론 라벨 줄", "최종보고서.md", "label", 3),
        ("plan", "7.5단계 리스크 토론 06-리스크토론-비중.md + 최종보고서 실행 계획 줄", "06-리스크토론-비중.md", "plan", 4),
        ("readme", "8단계 README.md 갱신", "README.md", "exists", 5),
        ("check", "9단계 형식 검사 PASS + 표본 검사 결과 기록", "최종보고서.md", "report_check", 6),
        ("ledger", "9.5단계 판단 원장 기록", None, "ledger", 7),
    ],
    "investment-research": [
        ("context", "과거 판단·교훈 확인(put --key lessons)", None, "has_blob:lessons", 0),
        ("factsheet", "팩트시트(put --key factsheet)", None, "has_blob:factsheet", 0),
        ("report", "보고서 작성(start --report 또는 done --file 로 경로 지정)", None, "label", 1),
        ("check", "형식 검사 PASS + 표본 검사 결과 기록", None, "report_check", 2),
        ("ledger", "판단 원장 기록", None, "ledger", 3),
    ],
}


def state_path(company: str, skill: str) -> str:
    return os.path.join(REPORTS, company, f".run-state-{skill}.json")


def _load(company: str, skill: str) -> dict:
    path = state_path(company, skill)
    if not os.path.exists(path):
        raise NoDataError(f"{company} 의 {skill} 실행 상태가 없습니다(start 로 시작).")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(state: dict) -> None:
    path = state_path(state["company"], state["skill"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _steps(state: dict) -> list:
    return SKILL_STEPS[state["skill"]]


def _artifact(state: dict, step: tuple, file_arg: str = "") -> str:
    """단계 산출물의 실제 경로. --file 로 준 경로가 우선(research 보고서처럼 이름이 날짜를 품는 경우)."""
    if file_arg:
        return file_arg
    if step[2]:
        return os.path.join(REPORTS, state["company"], step[2])
    return state.get("files", {}).get(step[0], "") or state.get("report", "")


# ---------------------------------------------------------------------------
# 검증: 산출물이 '끝난 상태'인지
# ---------------------------------------------------------------------------

def validate(state: dict, step: tuple, path: str) -> str:
    """통과하면 '', 아니면 실패 이유."""
    kind = step[3]
    if kind.startswith("has_blob:"):
        key = kind.split(":", 1)[1]
        return "" if state.get("blobs", {}).get(key) else f"put --key {key} 로 입력을 먼저 저장하세요."
    if kind == "ledger":
        rid = f"{state['started'][:10]}-{state['ticker']}-{state['skill']}"
        return "" if any(r["id"] == rid for r in dl._read(dl.LEDGER)) else f"원장에 {rid} 가 없습니다(add --from-report)."
    if not path or not os.path.exists(path):
        return f"산출물이 없습니다: {path or '(경로 미지정 — --file 로 지정)'}"
    with open(path, encoding="utf-8") as f:
        text = rc._norm(f.read())
    if kind == "exists":
        return "" if text.strip() else "빈 파일입니다."
    if kind == "view":
        views = rc._view_verdicts(path)
        if not views:
            return "`**관점 판단**:` 줄이 없습니다 — 저장이 끝나지 않았거나 중간에 끊긴 파일입니다."
        return "" if views[-1] in dl.VERDICTS else f"관점 판단 '{views[-1]}' 은 매수/관망/회피가 아닙니다."
    if kind == "rebuttal":
        views = rc._view_verdicts(path)
        ok = len(views) >= 4 and all(v in dl.VERDICTS for v in views)
        return "" if ok else f"관점 판단 4개가 필요합니다(찾은 것 {len(views)}개)."
    if kind == "label":
        try:
            dl.parse_label(text)
        except dl.ReportParseError as e:
            return f"결론 라벨 줄: {e}"
        return ""
    if kind == "plan":
        c = rc.Checker()
        rc.check_plan(c, os.path.join(REPORTS, state["company"], "최종보고서.md"), os.path.dirname(path))
        bad = [m for mark, m in c.items if mark != "✅"]
        return "; ".join(bad)
    if kind == "report_check":
        c = rc.check(path, state["skill"])
        bad = [m for mark, m in c.items if mark == "❌"]
        return "; ".join(bad)
    raise ValueError(f"알 수 없는 검증 종류: {kind}")


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------

def cmd_start(a):
    path = state_path(a.company, a.skill)
    if os.path.exists(path) and not a.force:
        st = _load(a.company, a.skill)
        nxt = ", ".join(s[0] for s in pending_steps(st)) or "없음"
        print(f"❌ {a.company} 의 {a.skill} 실행이 이미 진행 중입니다(시작 {st['started']}, 다음 단계 "
              f"{nxt}). 이어서 하려면 status/next, 버리고 새로 하려면 --force.")
        sys.exit(1)
    state = {"company": a.company, "ticker": a.ticker, "skill": a.skill, "started": _now(),
             "steps": {s[0]: {"status": "대기", "attempts": 0} for s in SKILL_STEPS[a.skill]},
             "blobs": {}, "files": {}, "log": []}
    if a.report:
        state["report"] = a.report
    state["log"].append(f"{_now()} start")
    _save(state)
    print(f"✅ 실행 상태 시작: {path}")
    print(f"   다음 단계: {', '.join(s[0] for s in pending_steps(state))}")


def pending_steps(state: dict) -> list:
    """가장 앞 묶음에서 아직 안 끝난 단계들(같은 묶음은 병렬로 해도 된다)."""
    left = [s for s in _steps(state) if state["steps"][s[0]]["status"] != "끝남"]
    return [s for s in left if s[4] == left[0][4]] if left else []


def cmd_status(a):
    st = _load(a.company, a.skill)
    print(f"{st['company']} ({st['ticker']}) {st['skill']} — 시작 {st['started']}")
    for s in _steps(st):
        info = st["steps"][s[0]]
        mark = {"끝남": "✅", "실패": "❌"}.get(info["status"], "⏳")
        extra = ""
        if info["status"] == "끝남" and info.get("sha"):
            path = _artifact(st, s)
            if path and os.path.exists(path) and _sha(path) != info["sha"]:
                extra = " · 끝난 뒤 산출물이 바뀜(의도한 수정인지 확인)"
        if info.get("attempts"):
            extra += f" · 시도 {info['attempts']}회"
        if info.get("error"):
            extra += f" · 마지막 오류: {info['error']}"
        if info.get("note"):
            extra += f" · {info['note']}"
        print(f"  {mark} {s[0]:<13} {s[1]}{extra}")
    pending = pending_steps(st)
    if pending:
        print(f"\n다음 단계{'(병렬 가능)' if len(pending) > 1 else ''}: " + ", ".join(s[0] for s in pending))
        for s in _steps(st):
            info = st["steps"][s[0]]
            if info["status"] != "끝남" and info.get("attempts", 0) >= MAX_ATTEMPTS:
                print(f"  ⚠️ {s[0]}: {MAX_ATTEMPTS}번 실패했습니다. 스킬의 폴백(Team Lead 대리 작성)을 쓰고 "
                      "산출물에 대리 작성임을 밝히세요.")
    else:
        print("\n모든 단계가 끝났습니다 — finish 로 상태를 정리하세요.")
    if st["blobs"]:
        print(f"저장된 입력: {', '.join(sorted(st['blobs']))} (재개할 때 다시 뽑지 말고 get 으로 같은 값을 쓴다)")


def cmd_next(a):
    pending = pending_steps(_load(a.company, a.skill))
    print(" ".join(s[0] for s in pending) if pending else "done")


def cmd_put(a):
    st = _load(a.company, a.skill)
    with open(a.file, encoding="utf-8") as f:
        st["blobs"][a.key] = {"saved": _now(), "text": f.read()}
    st["log"].append(f"{_now()} put {a.key}")
    _save(st)
    print(f"✅ {a.key} 저장 ({len(st['blobs'][a.key]['text'])}자)")


def cmd_get(a):
    st = _load(a.company, a.skill)
    blob = st["blobs"].get(a.key)
    if not blob:
        raise NoDataError(f"저장된 입력 '{a.key}' 가 없습니다.")
    sys.stdout.write(blob["text"])


def cmd_done(a):
    st = _load(a.company, a.skill)
    ids = [s[0] for s in _steps(st)]
    if a.step not in ids:
        raise SystemExit(f"❌ 단계 id 는 {', '.join(ids)} 중 하나")
    step = _steps(st)[ids.index(a.step)]
    path = _artifact(st, step, a.file)
    reason = validate(st, step, path)
    if reason:
        print(f"❌ {a.step} 를 끝난 것으로 기록하지 않았습니다: {reason}")
        sys.exit(1)
    info = st["steps"][a.step]
    info.update(status="끝남", finished=_now(), error="", note=a.note or info.get("note", ""))
    if path and os.path.exists(path):
        info["sha"] = _sha(path)
    if a.file:
        st["files"][a.step] = a.file
    # 앞 단계를 다시 끝냈으면, 더 뒤 묶음에서 이미 끝났던 단계는 다시 해야 한다(같은 묶음은 병렬이라 건드리지 않음).
    reset = [s[0] for s in _steps(st) if s[4] > step[4] and st["steps"][s[0]]["status"] == "끝남"]
    for i in reset:
        st["steps"][i].update(status="대기", note=f"앞 단계 {a.step} 가 다시 끝나 재실행 필요")
    st["log"].append(f"{_now()} done {a.step}" + (f" (재실행 필요: {', '.join(reset)})" if reset else ""))
    _save(st)
    print(f"✅ {a.step} 끝남" + (f" — 뒤 단계 재실행 필요: {', '.join(reset)}" if reset else ""))
    pending = pending_steps(st)
    print(f"   다음 단계: {', '.join(s[0] for s in pending)}" if pending else "   모든 단계 끝 — finish 로 정리")


def cmd_fail(a):
    st = _load(a.company, a.skill)
    if a.step not in st["steps"]:
        raise SystemExit(f"❌ 단계 id 는 {', '.join(st['steps'])} 중 하나")
    info = st["steps"][a.step]
    info["attempts"] = info.get("attempts", 0) + 1
    info.update(status="실패", error=a.error.replace("\n", " ")[:300])
    st["log"].append(f"{_now()} fail {a.step}: {info['error']}")
    _save(st)
    print(f"❌ {a.step} 실패 기록(시도 {info['attempts']}회): {info['error']}")
    if info["attempts"] >= MAX_ATTEMPTS:
        print(f"   {MAX_ATTEMPTS}번 실패 — 스킬의 폴백으로 Team Lead가 대리 작성하고, 산출물에 그 사실을 밝힌 뒤 done 하세요.")
    else:
        print("   같은 입력(get 으로 저장된 팩트시트 등)으로 이 단계만 다시 실행하세요.")


def cmd_finish(a):
    st = _load(a.company, a.skill)
    left = [s[0] for s in _steps(st) if st["steps"][s[0]]["status"] != "끝남"]
    if left:
        print(f"❌ 아직 끝나지 않은 단계: {', '.join(left)}")
        sys.exit(1)
    os.remove(state_path(a.company, a.skill))
    print(f"✅ {a.company} {a.skill} 실행 완료 — 상태 파일을 지웠습니다(최종 커밋에 남기지 않음).")


def main():
    p = argparse.ArgumentParser(description="리서치 실행 상태(중단 후 이어서 실행).")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--company", required=True, help="회사명(보고서 폴더명)")
        sp.add_argument("--skill", default="investment-team", choices=list(SKILL_STEPS))
        return sp

    ps = common(sub.add_parser("start", help="새 실행 시작"))
    ps.add_argument("--ticker", required=True)
    ps.add_argument("--report", default="", help="investment-research 보고서 경로(이름에 날짜가 들어가는 경우)")
    ps.add_argument("--force", action="store_true", help="진행 중인 상태를 버리고 새로 시작")
    common(sub.add_parser("status", help="단계별 상태"))
    common(sub.add_parser("next", help="다음 단계 id"))
    pp_ = common(sub.add_parser("put", help="입력 저장(팩트시트·교훈·기준선 등)"))
    pp_.add_argument("--key", required=True)
    pp_.add_argument("--file", required=True)
    pg = common(sub.add_parser("get", help="저장된 입력 출력"))
    pg.add_argument("--key", required=True)
    pd = common(sub.add_parser("done", help="산출물 검증 후 단계 끝남 기록"))
    pd.add_argument("--step", required=True)
    pd.add_argument("--file", default="", help="산출물 경로(기본: 단계 정의의 파일)")
    pd.add_argument("--note", default="", help="예: 'Team Lead 대리 작성'")
    pf = common(sub.add_parser("fail", help="단계 실패 기록"))
    pf.add_argument("--step", required=True)
    pf.add_argument("--error", required=True)
    common(sub.add_parser("finish", help="모두 끝났으면 상태 삭제"))

    a = p.parse_args()
    {"start": cmd_start, "status": cmd_status, "next": cmd_next, "put": cmd_put, "get": cmd_get,
     "done": cmd_done, "fail": cmd_fail, "finish": cmd_finish}[a.cmd](a)


if __name__ == "__main__":
    run(main)
