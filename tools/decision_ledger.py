#!/usr/bin/env python3
"""투자 판단 원장 — 리포트의 판단을 기록하고, 시간이 지난 뒤 수익률·알파로 채점하고, 회고를 남긴다.

외부 종속성 없음(stdlib + curl). 가격은 Yahoo Finance 차트 API(수정종가: 배당·분할 반영).

흐름:
  1) add     리포트를 쓸 때 판단(매수/관망/회피)·확신도·내재가치·반증 조건을 기록한다.
  2) settle  평가 시점(3M/6M/12M/36M)이 지난 판단을 채점한다.
             진입가 = 기록일 '다음' 거래일 종가(리포트 작성일 장 마감 뒤 정보를 봤을 수 있으므로).
             기간이 다 지나지 않은 판단은 건드리지 않는다(조기 정산 금지).
  3) review  채점 결과를 보고 논지 상태(유지/훼손/불명)와 2~4문장 회고를 남긴다.
  4) show    같은 종목을 다시 리서치할 때 과거 판단·결과·회고를 꺼내 본다.
  5) summary 판단별 적중률·평균 알파, 확신도 보정, 스킬별 비교, 운/실력 4분면.

판단은 앞으로 기록하는 것만 채점하므로, LLM이 학습 데이터로 미래를 이미 아는 문제(백테스트의 함정)가 없다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)의
  memory/log.py·memory/settlement.py·backtest.py 를 가치투자 리포트용으로 변형.

저장 파일(사람이 읽고 git diff로 추적할 수 있게 CSV):
  reports/decision-ledger.csv    판단 기록(추가만, 수정하지 않음)
  reports/decision-outcomes.csv  평가 시점별 채점 + 회고

사용법:
    python3 tools/decision_ledger.py add --ticker 000660 --name SK하이닉스 --skill investment-team \\
        --report reports/SK하이닉스/최종보고서.md --verdict 관망 --conviction 4 \\
        --iv-low 180000 --iv-high 220000 --thesis "HBM 리더십 유지" --falsifier "HBM 점유율 40% 미만"
    python3 tools/decision_ledger.py settle
    python3 tools/decision_ledger.py review --id 2026-10-27-000660-investment-team --horizon 3M \\
        --thesis-status 유지 --note "..."
    python3 tools/decision_ledger.py show 000660
    python3 tools/decision_ledger.py summary
    python3 tools/decision_ledger.py list

종료 코드: 0 정상 / 3 데이터 없음 / 4 가격 조회 장애(일부라도) — tools/_us_common.py 와 같은 규칙.
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import calendar
import csv
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

from _us_common import EXIT_UNAVAILABLE, NoDataError, UnavailableError, get_json, run

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR = os.environ.get("DECISION_LEDGER_DIR") or os.path.join(_ROOT, "reports")
LEDGER = os.path.join(_DIR, "decision-ledger.csv")
OUTCOMES = os.path.join(_DIR, "decision-outcomes.csv")

LEDGER_FIELDS = ["id", "기록일", "종목", "티커", "심볼", "시장", "통화", "스킬", "리포트", "판단", "확신도",
                 "기록시점가", "내재가치하단", "내재가치상단", "벤치마크", "핵심논지", "반증조건"]
OUTCOME_FIELDS = ["id", "구간", "진입일", "진입가", "평가일", "평가가", "수익률", "벤치마크수익률", "알파",
                  "방향적중", "내재가치위치", "정산일", "논지상태", "회고"]

VERDICTS = {"매수": 1, "관망": 0, "회피": -1}
HORIZONS = {"3M": 3, "6M": 6, "12M": 12, "36M": 36}
THESIS_STATES = ("유지", "훼손", "불명")

# 벤치마크: 수정종가로 배당까지 반영되도록 지수가 아니라 지수 추종 ETF를 쓴다(종목도 수정종가로 비교하므로).
BENCHMARKS = {
    "KOSPI": "069500.KS",    # KODEX 200
    "KOSDAQ": "229200.KS",   # KODEX 코스닥150
    "US": "SPY",
    "HK": "2800.HK",         # Tracker Fund (항셍)
    "CN": "510300.SS",       # CSI300 ETF
    "JP": "1306.T",          # TOPIX ETF
}
_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"


# ---------------------------------------------------------------------------
# 파일
# ---------------------------------------------------------------------------

def _read(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write(path: str, fields: list, rows: list) -> None:
    """임시 파일에 쓴 뒤 교체(중간에 죽어도 원장이 깨지지 않게)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def _append(path: str, fields: list, row: dict) -> None:
    rows = _read(path)
    rows.append(row)
    _write(path, fields, rows)


# ---------------------------------------------------------------------------
# 종목·시장·가격
# ---------------------------------------------------------------------------

def market_of(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(".KS"):
        return "KOSPI"
    if s.endswith(".KQ"):
        return "KOSDAQ"
    if s.endswith(".HK"):
        return "HK"
    if s.endswith((".SS", ".SZ")):
        return "CN"
    if s.endswith(".T"):
        return "JP"
    return "US"


def resolve_symbol(ticker: str):
    """입력 코드 → (Yahoo 심볼, 통화, 현재가). global_stock_data 의 규칙을 그대로 쓴다(6자리=한국, .KS→.KQ 재시도)."""
    from global_stock_data import _resolve
    symbol, meta = _resolve(ticker)
    if not symbol:
        raise NoDataError(f"{ticker} 를 Yahoo Finance에서 찾지 못했습니다(티커 확인 또는 네트워크 확인).")
    return symbol, meta.get("currency", ""), meta.get("regularMarketPrice")


def fetch_closes(symbol: str, start: str, end: str) -> list:
    """[(날짜, 종가, 수정종가)] — start~end(포함), 거래소 현지 날짜 기준, 오늘 봉(장중 가격) 제외."""
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    p2 = int((datetime.strptime(end, "%Y-%m-%d") + timedelta(days=2)).replace(tzinfo=timezone.utc).timestamp())
    data = get_json(_YAHOO + symbol, {"period1": p1, "period2": p2, "interval": "1d", "events": "div,split"},
                    headers={"User-Agent": "Mozilla/5.0"})
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        err = ((data.get("chart") or {}).get("error") or {}).get("description", "")
        raise NoDataError(f"{symbol} 가격 데이터 없음 {err}".strip())
    offset = (result.get("meta") or {}).get("gmtoffset", 0)
    stamps = result.get("timestamp") or []
    close = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or close
    today = date.today().strftime("%Y-%m-%d")
    rows = []
    for ts, c, a in zip(stamps, close, adj):
        if c is None or a is None or c <= 0:
            continue
        d = datetime.fromtimestamp(ts + offset, tz=timezone.utc).strftime("%Y-%m-%d")
        if start <= d <= end and d < today:
            rows.append((d, c, a))
    return sorted(rows)


def add_months(d: str, months: int) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d")
    y, m = divmod(dt.month - 1 + months, 12)
    y, m = dt.year + y, m + 1
    return date(y, m, min(dt.day, calendar.monthrange(y, m)[1])).strftime("%Y-%m-%d")


def _asof(rows: list, d: str):
    """d 이하 마지막 봉(휴장일이 다른 시장끼리 맞추기 위함)."""
    hit = [r for r in rows if r[0] <= d]
    return hit[-1] if hit else None


def evaluate(entry_row: dict, horizon: str, stock: list, bench: list):
    """한 판단·한 구간의 채점. 기간이 다 거래되지 않았으면 None."""
    after = [r for r in stock if r[0] > entry_row["기록일"]]
    if not after:
        return None
    entry = after[0]
    target = add_months(entry[0], HORIZONS[horizon])
    exits = [r for r in stock if r[0] >= target]
    if not exits:
        return None
    exit_ = exits[0]
    b_in, b_out = _asof(bench, entry[0]), _asof(bench, exit_[0])
    # 벤치마크가 청산일까지 거래돼 있어야 같은 기간 비교가 된다.
    if not b_in or not b_out or not bench or bench[-1][0] < exit_[0]:
        return None
    ret = exit_[2] / entry[2] - 1
    bret = b_out[2] / b_in[2] - 1
    alpha = ret - bret
    direction = VERDICTS[entry_row["판단"]]
    hit = "-" if direction == 0 else ("적중" if alpha * direction > 0 else "빗나감")
    return {
        "id": entry_row["id"], "구간": horizon, "진입일": entry[0], "진입가": fmt_price(entry[1]),
        "평가일": exit_[0], "평가가": fmt_price(exit_[1]), "수익률": f"{ret:+.4f}",
        "벤치마크수익률": f"{bret:+.4f}", "알파": f"{alpha:+.4f}", "방향적중": hit,
        "내재가치위치": iv_position(exit_[1], entry_row.get("내재가치하단"), entry_row.get("내재가치상단")),
        "정산일": date.today().strftime("%Y-%m-%d"), "논지상태": "", "회고": "",
    }


def fmt_price(x: float) -> str:
    """가격을 지수 표기 없이(소수 4자리까지, 끝의 0 제거). 54400 → "54400", 243.4 → "243.4"."""
    return f"{x:.4f}".rstrip("0").rstrip(".")


def iv_position(price: float, low: str, high: str) -> str:
    """평가일 종가(수정 전)가 기록한 내재가치 범위의 어디에 있나."""
    try:
        lo, hi = float(low), float(high or low)
    except (TypeError, ValueError):
        return "-"
    if price < lo:
        return "하단 미만"
    if price > hi:
        return "상단 초과"
    return "범위 안"


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------

def cmd_add(a):
    if a.verdict not in VERDICTS:
        raise SystemExit(f"❌ --verdict 는 {'/'.join(VERDICTS)} 중 하나")
    if not 1 <= a.conviction <= 5:
        raise SystemExit("❌ --conviction 은 1~5")
    rec_date = a.date or date.today().strftime("%Y-%m-%d")
    datetime.strptime(rec_date, "%Y-%m-%d")
    if rec_date > date.today().strftime("%Y-%m-%d"):
        raise SystemExit("❌ 미래 날짜로 기록할 수 없습니다.")
    if a.report and not os.path.exists(os.path.join(_ROOT, a.report)):
        print(f"⚠️ 리포트 파일이 아직 없습니다: {a.report} (경로 확인)")

    try:
        symbol, currency, price = resolve_symbol(a.ticker)
    except (NoDataError, UnavailableError) as e:
        # 기록은 가격 조회 실패로 막지 않는다. 심볼은 정산 때 다시 확인한다.
        print(f"⚠️ 종목 확인 실패({e}) — 입력 티커 그대로 기록하고 정산 때 다시 확인합니다.")
        symbol, currency, price = a.ticker.upper(), "", None
    market = market_of(symbol)
    rid = f"{rec_date}-{re.sub(r'[^0-9A-Za-z.]', '', a.ticker.upper())}-{a.skill}"
    if any(r["id"] == rid for r in _read(LEDGER)):
        raise SystemExit(f"❌ 이미 기록된 판단입니다: {rid} (같은 날·종목·스킬은 한 번만 — 집계가 부풀지 않게)")

    row = {
        "id": rid, "기록일": rec_date, "종목": a.name, "티커": a.ticker.upper(), "심볼": symbol,
        "시장": market, "통화": currency, "스킬": a.skill, "리포트": a.report or "", "판단": a.verdict,
        "확신도": str(a.conviction), "기록시점가": fmt_price(price) if price else "",
        "내재가치하단": a.iv_low or "", "내재가치상단": a.iv_high or "",
        "벤치마크": a.benchmark or BENCHMARKS.get(market, "SPY"),
        "핵심논지": a.thesis or "", "반증조건": a.falsifier or "",
    }
    _append(LEDGER, LEDGER_FIELDS, row)
    print(f"✅ 기록: {rid}")
    print(f"   {a.name}({symbol}, {market}) {a.verdict} {'★' * a.conviction} | 벤치마크 {row['벤치마크']}")
    print(f"   진입가는 {rec_date} 다음 거래일 종가로 정산 때 확정됩니다. 평가 시점: {', '.join(HORIZONS)}")


def cmd_settle(a):
    ledger = _read(LEDGER)
    if not ledger:
        raise NoDataError(f"기록된 판단이 없습니다: {LEDGER}")
    outcomes = _read(OUTCOMES)
    done = {(o["id"], o["구간"]) for o in outcomes}
    today = date.today().strftime("%Y-%m-%d")
    new, failed, waiting = [], [], 0
    for row in ledger:
        todo = [h for h in HORIZONS if (row["id"], h) not in done]
        # 가장 이른 미정산 구간의 목표일이 아직 안 왔으면 가격 조회 없이 넘긴다.
        if not todo or add_months(row["기록일"], HORIZONS[todo[0]]) >= today:
            waiting += len(todo)
            continue
        last_target = add_months(row["기록일"], HORIZONS[todo[-1]])
        end = min(add_months(last_target, 1), today)
        start = (datetime.strptime(row["기록일"], "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        try:
            stock = fetch_closes(row["심볼"], start, end)
            bench = fetch_closes(row["벤치마크"], start, end)
        except (NoDataError, UnavailableError) as e:
            failed.append((row["id"], str(e)))
            continue
        for h in todo:
            result = evaluate(row, h, stock, bench)
            if result is None:
                waiting += 1
            else:
                new.append(result)
    if new:
        _write(OUTCOMES, OUTCOME_FIELDS, outcomes + new)
    print(f"정산 {len(new)}건 · 대기 {waiting}건 · 실패 {len(failed)}건")
    for o in new:
        print(f"  ✅ {o['id']} [{o['구간']}] {o['진입일']}→{o['평가일']} 수익률 {_pct(o['수익률'])} "
              f"알파 {_pct(o['알파'])} {o['방향적중']} | 내재가치 {o['내재가치위치']}")
    if new:
        print("  → 각 건에 review 로 논지 상태와 회고를 남기세요(thesis-tracker 로 반증 조건 점검).")
    for rid, err in failed:
        print(f"  ❌ {rid}: {err}")
    if failed:
        print("  실패 건은 다음 정산 때 다시 시도합니다. 수익률을 추정해 채우지 마세요.")
        sys.exit(EXIT_UNAVAILABLE)


def cmd_review(a):
    if a.thesis_status not in THESIS_STATES:
        raise SystemExit(f"❌ --thesis-status 는 {'/'.join(THESIS_STATES)} 중 하나")
    outcomes = _read(OUTCOMES)
    target = [o for o in outcomes if o["id"] == a.id and o["구간"] == a.horizon]
    if not target:
        raise NoDataError(f"정산된 결과가 없습니다: {a.id} [{a.horizon}] — settle 먼저 실행")
    target[0]["논지상태"] = a.thesis_status
    target[0]["회고"] = a.note.replace("\n", " ").strip()
    _write(OUTCOMES, OUTCOME_FIELDS, outcomes)
    print(f"✅ 회고 기록: {a.id} [{a.horizon}] 논지 {a.thesis_status}")


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "-"


def cmd_show(a):
    key = a.ticker.upper()
    rows = [r for r in _read(LEDGER) if key in (r["티커"], r["심볼"].upper()) or r["종목"] == a.ticker]
    if not rows:
        raise NoDataError(f"{a.ticker} 의 과거 판단 기록이 없습니다.")
    outs = _read(OUTCOMES)
    print(f"과거 판단: {rows[0]['종목']} ({rows[0]['심볼']}) — 최근 순")
    for r in sorted(rows, key=lambda r: r["기록일"], reverse=True):
        iv = f"{r['내재가치하단']}~{r['내재가치상단']} {r['통화']}" if r["내재가치하단"] else "-"
        print(f"\n[{r['기록일']} | {r['스킬']} | {r['판단']} {'★' * int(r['확신도'] or 0)} | 내재가치 {iv}]")
        if r["핵심논지"]:
            print(f"  논지: {r['핵심논지']}")
        if r["반증조건"]:
            print(f"  반증 조건: {r['반증조건']}")
        print(f"  리포트: {r['리포트']}")
        mine = sorted((o for o in outs if o["id"] == r["id"]), key=lambda o: HORIZONS[o["구간"]])
        if not mine:
            print("  결과: 미정산")
        for o in mine:
            print(f"  [{o['구간']}] 수익률 {_pct(o['수익률'])} 알파 {_pct(o['알파'])} {o['방향적중']} "
                  f"| 내재가치 {o['내재가치위치']} | 논지 {o['논지상태'] or '미검토'}")
            if o["회고"]:
                print(f"       회고: {o['회고']}")


def summarize(ledger: list, outcomes: list) -> dict:
    """구간별 집계. 매수·회피는 방향 적중률, 관망은 방향 주장이 없으므로 적중률 없음."""
    by_id = {r["id"]: r for r in ledger}
    out = {}
    for h in HORIZONS:
        rows = [(by_id[o["id"]], o) for o in outcomes if o["구간"] == h and o["id"] in by_id]
        if not rows:
            continue
        sec = {"verdict": {}, "conviction": {}, "skill": {}, "quadrant": {}, "n": len(rows)}
        for v, d in VERDICTS.items():
            alphas = [float(o["알파"]) for r, o in rows if r["판단"] == v]
            if alphas:
                hits = [a_ * d > 0 for a_ in alphas] if d else None
                sec["verdict"][v] = (len(alphas), sum(hits) / len(hits) if hits else None,
                                     sum(alphas) / len(alphas))
        # 확신도 보정: 판단 방향을 곱한 알파(맞힌 쪽이 +). 관망은 방향이 없어 제외.
        for r, o in rows:
            d = VERDICTS[r["판단"]]
            if d:
                sec["conviction"].setdefault(r["확신도"], []).append(float(o["알파"]) * d)
                sec["skill"].setdefault(r["스킬"], []).append(float(o["알파"]) * d)
            if o["논지상태"] in ("유지", "훼손") and d:
                up = float(o["알파"]) * d > 0
                q = {("유지", True): "실력", ("유지", False): "인내 구간",
                     ("훼손", True): "운", ("훼손", False): "오판"}[(o["논지상태"], up)]
                sec["quadrant"][q] = sec["quadrant"].get(q, 0) + 1
        out[h] = sec
    return out


def cmd_summary(a):
    ledger, outcomes = _read(LEDGER), _read(OUTCOMES)
    if not ledger:
        raise NoDataError("기록된 판단이 없습니다.")
    print(f"판단 {len(ledger)}건 · 정산 결과 {len(outcomes)}건 · "
          f"회고 미작성 {sum(1 for o in outcomes if not o['논지상태'])}건")
    stats = summarize(ledger, outcomes)
    if not stats:
        print("아직 평가 시점이 지난 판단이 없습니다.")
        return
    for h, sec in stats.items():
        print(f"\n[{h}] 정산 {sec['n']}건")
        for v, (n, hit, mean) in sec["verdict"].items():
            hit_s = f"방향 적중 {hit:.0%}" if hit is not None else "방향 주장 없음"
            print(f"  {v}: n={n}, {hit_s}, 평균 알파 {mean * 100:+.1f}%")
        if sec["conviction"]:
            print("  확신도 보정(판단 방향 기준 알파, 높을수록 잘 맞음):")
            for c in sorted(sec["conviction"]):
                vals = sec["conviction"][c]
                print(f"    {'★' * int(c)}: n={len(vals)}, 평균 {sum(vals) / len(vals) * 100:+.1f}%")
        if sec["skill"]:
            print("  스킬별(판단 방향 기준 알파):")
            for s, vals in sorted(sec["skill"].items()):
                print(f"    {s}: n={len(vals)}, 평균 {sum(vals) / len(vals) * 100:+.1f}%")
        if sec["quadrant"]:
            print("  운/실력 4분면(회고 완료·매수/회피만): " +
                  ", ".join(f"{k} {v}" for k, v in sec["quadrant"].items()))
    print("\n주의: 표본이 적으면 우연이 크게 작용한다. 알파는 수정종가 기준, 벤치마크는 지수 추종 ETF.")


def cmd_list(a):
    ledger = _read(LEDGER)
    if not ledger:
        raise NoDataError("기록된 판단이 없습니다.")
    outs = _read(OUTCOMES)
    for r in ledger:
        settled = sorted((o["구간"] for o in outs if o["id"] == r["id"]), key=lambda h: HORIZONS[h])
        print(f"{r['기록일']} {r['종목']}({r['심볼']}) {r['판단']} {'★' * int(r['확신도'] or 0)} "
              f"[{r['스킬']}] 정산: {', '.join(settled) or '-'}")


def main():
    p = argparse.ArgumentParser(description="투자 판단 원장: 기록 → 정산 → 회고.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="리포트 판단 기록")
    pa.add_argument("--ticker", required=True, help="005930 / AAPL / 0700 등(global_stock_data 규칙)")
    pa.add_argument("--name", required=True, help="종목명(보고서 폴더명과 같게)")
    pa.add_argument("--skill", required=True, help="investment-team / investment-research / investment-checklist 등")
    pa.add_argument("--report", default="", help="리포트 경로(저장소 기준)")
    pa.add_argument("--verdict", required=True, help="매수 / 관망 / 회피")
    pa.add_argument("--conviction", type=int, default=3, help="확신도 1~5(★ 개수)")
    pa.add_argument("--iv-low", default="", help="내재가치 하단(현지 통화)")
    pa.add_argument("--iv-high", default="", help="내재가치 상단")
    pa.add_argument("--thesis", default="", help="핵심 논지 한 줄")
    pa.add_argument("--falsifier", default="", help="반증 조건(이게 보이면 논지가 틀린 것)")
    pa.add_argument("--benchmark", default="", help="벤치마크 심볼 지정(기본: 시장별 ETF)")
    pa.add_argument("--date", default="", help="기록일(기본 오늘). 리포트 작성일과 같아야 함")

    sub.add_parser("settle", help="평가 시점이 지난 판단 채점")

    pr = sub.add_parser("review", help="정산 결과에 논지 상태·회고 기록")
    pr.add_argument("--id", required=True)
    pr.add_argument("--horizon", required=True, choices=list(HORIZONS))
    pr.add_argument("--thesis-status", required=True, help="유지 / 훼손 / 불명")
    pr.add_argument("--note", required=True, help="2~4문장: ①수치가 말해주는 것 ②논지의 맞은/틀린 부분 ③교훈 1개")

    ps = sub.add_parser("show", help="종목의 과거 판단·결과·회고")
    ps.add_argument("ticker", help="티커 또는 종목명")
    sub.add_parser("summary", help="집계")
    sub.add_parser("list", help="전체 목록")

    a = p.parse_args()
    {"add": cmd_add, "settle": cmd_settle, "review": cmd_review, "show": cmd_show,
     "summary": cmd_summary, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    run(main)
