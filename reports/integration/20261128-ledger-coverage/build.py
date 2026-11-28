"""고정한 main의 first-parent 이력으로 판단 원장 평가 가능 여부표를 생성한다."""
import csv
import io
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
BASE = "8056df5fc268bd918b2025fe0ea6a56c96ab8cc8"
LEDGER = "reports/decision-ledger.csv"
END = date(2026, 11, 27)
ZONES = {"US": "America/New_York", "JP": "Asia/Tokyo", "KOSPI": "Asia/Seoul"}
HOLIDAYS = {"US": {date(2026, 11, 26)}, "JP": {date(2026, 11, 3), date(2026, 11, 23)}, "KOSPI": set()}
EVIDENCE = {
    "2026-10-28-MSFT-investment-team": "#137 축소·#138 교체",
    "2026-11-02-ADBE-investment-team": "#136 매수·#138 교체",
    "2026-10-31-NFLX-investment-team": "#139 관망",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


@lru_cache(None)
def history(path):
    return git("log", "--first-parent", "--reverse", "--format=%H %cI",
               BASE, "--", path).splitlines()


def generate():
    ledger = list(csv.DictReader(io.StringIO(git("show", BASE + ":" + LEDGER))))
    first = {}
    for line in history(LEDGER):
        rev, stamp = line.split()
        for r in csv.DictReader(io.StringIO(git("show", rev + ":" + LEDGER))):
            first.setdefault(r["id"], (rev, stamp, r))
    counts = Counter(r["티커"] for r in ledger)
    out, calendars = [], []
    for r in ledger:
        key, path, market = r["id"], r["리포트"], r["시장"]
        rev, stamp, original = first[key]
        assert all(original[k] == r[k] for k in ("티커", "시장", "판단", "리포트", "스킬"))
        blob = git("rev-parse", rev + ":" + path).strip()
        zone = ZoneInfo(ZONES[market])
        def local(ts):
            return datetime.fromisoformat(ts).astimezone(zone).date()
        changes = history(path)
        index = next(i for i, item in enumerate(reversed(changes))
                     if subprocess.run(["git", "merge-base", "--is-ancestor", item.split()[0], rev],
                                       cwd=ROOT).returncode == 0)
        pos = len(changes) - 1 - index
        source, source_time = changes[pos].split()
        assert git("rev-parse", source + ":" + path).strip() == blob
        next_date = local(changes[pos+1].split()[1]) if pos+1 < len(changes) else None
        day = local(stamp) + timedelta(days=1)
        sessions = set()
        elapsed = 0
        while day <= END:
            if day.weekday() < 5 and day not in HOLIDAYS[market]:
                elapsed += 1
                if next_date is None or day < next_date:
                    sessions.add(day)
            day += timedelta(days=1)
        calendars.append(sessions)
        control = {"매수":"현금·벤치마크", "관망":"즉시·조건부·현금", "회피":"미편입·가상편입"}[r["판단"]]
        out.append(dict(id=key, ticker=r["티커"], market=market, skill=r["스킬"], opinion=r["판단"],
                        report=path, main_revision=source, report_blob=blob, report_time=source_time,
                        ledger_time=stamp, next_version_local=next_date or "", benchmark=r["벤치마크"],
                        controls=control, ticker_rows=counts[r["티커"]],
                        start=min(sessions) if sessions else "", end=max(sessions) if sessions else "",
                        sessions=len(sessions), elapsed_sessions=elapsed,
                        elapsed_windows="|".join(str(h) for h in (5,20,60) if elapsed >= h),
                        mature_windows="|".join(str(h) for h in (5,20,60) if len(sessions)>=h),
                        evidence=EVIDENCE.get(key,"사례 미연결"),
                        case_observations={"2026-10-28-MSFT-investment-team":"10/29~11/19, 11/06~11/19",
                                           "2026-11-02-ADBE-investment-team":"11/04 또는 11/06~11/27, 11/06~11/19",
                                           "2026-10-31-NFLX-investment-team":"11/02~11/20"}.get(key,"미검증"), trigger_status="사례별 일부 확인" if key in EVIDENCE else "미판정",
                        missing="체크리스트 후속 심층 조건·가격" if r["스킬"]=="investment-checklist" else "조건·가격·대조군의 고정창 패널"))
    for i, row in enumerate(out):
        row["overlap_rows"] = sum(1 for j, other in enumerate(out) if i != j and
                                  other["market"] == row["market"] and calendars[i] & calendars[j])
    assert len(out) == len({r["id"] for r in out}) == len(ledger)
    return out


if __name__ == "__main__":
    rows = generate()
    with Path(__file__).with_name("coverage.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(len(rows), len({r["ticker"] for r in rows}), Counter(r["opinion"] for r in rows))
    print({n:sum(r["sessions"] >= n for r in rows) for n in (1,5,20,60)})
    print("개정 이후 포함", {n:sum(r["elapsed_sessions"] >= n for r in rows) for n in (5,20,60)})
    print("반복 티커",len({r["ticker"] for r in rows if r["ticker_rows"]>1}),
          "중첩 행",sum(r["overlap_rows"]>0 for r in rows))
