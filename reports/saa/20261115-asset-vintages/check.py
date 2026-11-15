"""Compare archived monthly endpoints for annual five-asset training windows."""
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from datetime import date
from calendar import monthrange
from decimal import Decimal

ROOT = Path(__file__).resolve().parent
SERIES = ("NASDAQXNDX", "DEXKOUS")

def month_shift(y, offset):
    index = y * 12 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"

def fetch(pair):
    series, vintage = pair
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}" if vintage == "reference"
           else f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={vintage}")
    path = ROOT / "raw" / f"{series}-{vintage}.csv"
    if vintage == "reference":
        path = SNAPSHOT / "raw" / "fred" / f"{series}.csv"
        if not path.exists():
            raise ValueError("original snapshot missing")
    failure_path = ROOT / "raw" / f"{series}-{vintage}.error.json"
    if failure_path.exists():
        return pair, json.loads(failure_path.read_text())
    for attempt in range(3):
        try:
            if not path.exists():
                with urlopen(url, timeout=20) as response:
                    data = response.read()
                header = data.decode().splitlines()[0]
                expected = f"observation_date,{series}" + ("" if vintage == "reference" else "_" + vintage.replace("-", ""))
                if header.strip() != expected:
                    raise ValueError(f"unexpected header {header[:80]}")
                path.write_bytes(data)
            data = path.read_bytes()
            observations = {}
            for day, value in list(csv.reader(io.StringIO(data.decode())))[1:]:
                if value not in ("", "."):
                    observations[day] = Decimal(value)
            return pair, dict(url=url, sha256=hashlib.sha256(data).hexdigest(), values=observations)
        except Exception as exc:
            if attempt == 2:
                result = dict(url=url, error=str(exc))
                failure_path.write_text(json.dumps(result))
                return pair, result

def endpoints(values):
    result = {}
    for day in sorted(values):
        result[day[:7]] = (day, values[day])
    for month, (day, value) in list(result.items()):
        y,m = map(int, month.split("-"))
        if (date(y,m,monthrange(y,m)[1])-date.fromisoformat(day)).days > 7:
            del result[month]
    return result

def main():
    global ROOT, SNAPSHOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    SNAPSHOT = Path(args.snapshot)
    ROOT = Path(args.work_dir)
    (ROOT / "raw").mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    for series in SERIES:
        digest = hashlib.sha256((SNAPSHOT / "raw" / "fred" / (series + ".csv")).read_bytes()).hexdigest()
        assert digest == next(row["sha256"] for row in manifest if row["source_id"] == series)
    pairs = [(s,d) for s in SERIES for d in ["reference"] + [f"{y}-12-30" for y in range(2016,2026)]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        downloaded = dict(pool.map(fetch,pairs))
    rows=[]
    for series in SERIES:
        reference = downloaded[series,"reference"]
        if "error" in reference:
            raise RuntimeError(reference["error"])
        latest = endpoints(reference["values"])
        for y in range(2017,2027):
            vintage=f"{y-1}-12-30"
            data=downloaded[series,vintage]
            row=dict(series=series,decision_month=f"{y}-01",vintage=vintage,url=data["url"],
                     reference_sha256=reference["sha256"])
            if "error" in data:
                row["error"]=data["error"]
            else:
                old=endpoints(data["values"])
                # 60 return months t-62..t-3 require one preceding endpoint.
                required=[month_shift(y,i) for i in range(-63,-2)]
                missing=[m for m in required if m not in old]
                diffs=[dict(month=m,previous_date=old[m][0],reference_date=latest[m][0],
                            previous_value=str(old[m][1]),reference_value=str(latest[m][1]))
                       for m in required if m in old and m in latest and old[m]!=latest[m]]
                row.update(sha256=data["sha256"],required_count=len(required),
                           missing=missing,differences=diffs)
            rows.append(row)
    (ROOT/"results.json").write_text(json.dumps(rows,indent=2)+"\n")
    for row in rows:
        print(row["series"],row["decision_month"],row.get("error") or
              f'missing={len(row["missing"])} changed={len(row["differences"])}')
if __name__=="__main__":
    main()
