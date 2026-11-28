"""Replay the first price leg using frozen report blobs and observed local closes."""
import csv
import re
import subprocess
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
COVERAGE = HERE.parent / "20261128-ledger-coverage" / "coverage.csv"


def read(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def build():
    bars = defaultdict(list)
    for bar in read(HERE / "bars.csv"):
        o, h, l, c = (Decimal(bar[key]) for key in ("open", "high", "low", "close"))
        assert 0 < l <= min(o, c) <= max(o, c) <= h
        bars[bar["ticker"]].append(bar)
    rows = []
    for item in read(COVERAGE):
        if "5" not in item["mature_windows"].split("|"):
            continue
        ticker = item["ticker"]
        result = dict(id=item["id"], report_blob=item["report_blob"], start=item["start"],
                      fifth="", first_level="", min_close="", first_low_touch="",
                      first_close_touch="", next_open="", status="스크리닝 판단")
        if item["skill"] == "investment-team":
            report = subprocess.check_output(
                ["git", "cat-file", "blob", item["report_blob"]], cwd=HERE, text=True)
            if ticker == "005930":
                assert "약 18만원 이하" in report
                level = Decimal(180000)
            else:
                match = re.search(r"\*\*분할 매수\*\*:\s*([\d,.]+)", report)
                assert match, item["id"]
                level = Decimal(match[1].replace(",", ""))
            window = bars[ticker]
            dates = [b["date"] for b in window]
            assert len(set(dates)) == 5 and dates == sorted(dates)
            assert dates[0] == item["start"] and dates[-1] <= item["end"]
            close_hits = [b for b in window if Decimal(b["close"]) <= level]
            low_hits = [b for b in window if Decimal(b["low"]) <= level]
            result.update(fifth=dates[-1], first_level=str(level),
                          min_close=min(Decimal(b["close"]) for b in window),
                          first_low_touch=low_hits[0]["date"] if low_hits else "",
                          status="종가 미도달")
            if close_hits:
                day = close_hits[0]["date"]
                idx = dates.index(day)
                result.update(first_close_touch=day,
                              next_open=window[idx+1]["open"] if idx < 4 else "",
                              status="1차 가격 충족" if ticker == "ADBE" else "재검토 필요")
        rows.append(result)
    assert len(rows) == len({r["id"] for r in rows}) == 32
    assert sum(map(len, bars.values())) == 115
    with (HERE / "results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(Counter(r["status"] for r in rows))


if __name__ == "__main__":
    build()
