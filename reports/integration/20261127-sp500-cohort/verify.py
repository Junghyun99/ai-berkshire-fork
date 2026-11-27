"""11월 20일 스크리닝과 27일 기준 원장을 티커 단위로 연결한다."""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCREEN = ROOT / "스크리닝/S&P500-후보풀/S&P500-부실배제결과-20261120.md"
archive = SCREEN.read_text()
appendix = archive.split("## 부록: 전 종목 요약표")[1].split("## 한계 고지")[0]
universe = {}
outcomes = Counter()
for line in appendix.splitlines():
    if not line.startswith("|") or "**" not in line:
        continue
    name, sector, *_, outcome = (s.strip() for s in line.strip("|").split("|"))
    ticker = re.search(r"\(([^()]+)\)$", name)[1].replace(".", "-")
    assert ticker not in universe
    universe[ticker] = (sector, "통과" in outcome)
    outcomes[outcome.strip("*")] += 1
assert outcomes == {"통과": 321, "통과 (데이터부족)": 7, "면제 통과": 9, "배제": 162}
missing = set(re.findall(r"^- .*?\(([A-Z]+)\):", archive.split("## 데이터 부족 (판정 불가)")[1].split("## 산업")[0], re.M))
assert len(missing) == 4 and missing.isdisjoint(universe)
with (ROOT / "reports/decision-ledger.csv").open() as f:
    ledger = [r for r in csv.DictReader(f) if r["기록일"] <= "2026-11-27"]
records = defaultdict(list)
for r in ledger:
    if (r["시장"], r["스킬"]) == ("US", "investment-team"):
        records[r["티커"].replace(".", "-")].append((r["기록일"], r["판단"]))
print("전체 행 / 고유 티커", len(ledger), len({r["티커"] for r in ledger}))
print("| 업종 | 판정 가능 | 통과 | 이전 | 당일 | 이후 | 당일·이후 합계 |")
print("|---|---:|---:|---:|---:|---:|---:|")
total = Counter()
judgments = Counter()
for sector in sorted({s for s, _ in universe.values()}):
    counts = Counter()
    for ticker, (group, passed) in universe.items():
        if group != sector:
            continue
        counts["all"] += 1
        if not passed:
            continue
        counts["pass"] += 1
        events = records.get(ticker, [])
        dates = [date for date, _ in events]
        counts["before"] += any(d < "2026-11-20" for d in dates)
        counts["same"] += "2026-11-20" in dates
        counts["after"] += any(d > "2026-11-20" for d in dates)
        recent = [event for event in events if event[0] >= "2026-11-20"]
        if recent:
            counts["recent"] += 1
            judgments[max(recent)[1]] += 1
    total.update(counts)
    print("|", sector, "|", " | ".join(str(counts[k]) for k in ("all","pass","before","same","after","recent")), "|")
print(dict(total), dict(judgments))
for label, condition in [
    ("이전과 당일·이후 중복", lambda t: universe.get(t, ("",False))[1] and min(records[t])[0] < "2026-11-20" <= max(records[t])[0]),
    ("당일·이후 통과표 밖", lambda t: not universe.get(t, ("",False))[1] and max(records[t])[0] >= "2026-11-20"),
]:
    print(label, sorted(t for t in records if condition(t)))
