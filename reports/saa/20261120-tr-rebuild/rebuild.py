"""Compare dividend amount and reinvestment conventions; research proxies."""
import argparse
import hashlib
import importlib.util
import json
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo

def gross_return(previous, current, dividend, method):
    if any(not v.is_finite() for v in (previous,current,dividend)):
        raise ValueError("Nonfinite input")
    if previous <= 0 or current <= 0 or dividend < 0 or dividend >= previous:
        raise ValueError("Invalid price/distribution")
    if method == "backward": return current/(previous-dividend)
    if method == "ex_close": return (current+dividend)/previous
    raise ValueError("Unknown method")

def rebuild(dates, close, dividends, method):
    if len(dates)!=len(close) or not dates or dates != sorted(set(dates)):
        raise ValueError("Invalid dates/price lengths")
    if any(not v.is_finite() or v<=0 for v in close): raise ValueError("Invalid price")
    missing={d for d in dividends if dates[0]<d<=dates[-1]}-set(dates)
    if missing: raise ValueError("Distribution without price: "+str(sorted(missing)))
    levels=[D(1)]
    for i in range(1,len(dates)):
        levels.append(levels[-1]*gross_return(close[i-1],close[i],dividends.get(dates[i],D(0)),method))
    return levels

def monthly(dates,levels):
    ends={}
    for day,value in zip(dates,levels): ends[day[:7]]=(day,value)
    months=sorted(ends)
    out={}
    for prev,cur in zip(months,months[1:]):
        # Reject gaps; output starts after first month-end baseline.
        y,m=map(int,prev.split("-")); yy,mm=map(int,cur.split("-"))
        if yy*12+mm!=y*12+m+1: raise ValueError("Missing month")
        out[cur]=ends[cur][1]/ends[prev][1]-1
    return out

def compare(a,b):
    if set(a)!=set(b) or not a:raise ValueError("Mismatched months")
    changes={m:(b[m]-a[m])*10000 for m in a}
    worst=max(changes,key=lambda m:abs(changes[m]))
    ratio=D(1)
    for m in a:ratio*=(1+b[m])/(1+a[m])
    return {"max_abs_monthly_difference_bp":abs(changes[worst]),
            "max_difference_month":worst,"signed_difference_at_max_bp":changes[worst],
            "terminal_wealth_difference_bp":(ratio-1)*10000}

def run(raw,yahoo,audit_dir):
    spec=importlib.util.spec_from_file_location("issuer_audit",audit_dir/"check.py")
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    manifest=json.loads((audit_dir/"results.json").read_text())
    for name,record in manifest["issuer_sources"].items():
        if audit.sha(raw/name)!=record["sha256"]:raise ValueError("Issuer hash mismatch: "+name)
    sheets,_=audit.xml_sheets(raw/"ief-download")
    official={
      "SPY":audit.unique((audit.date(r["D"],"%m/%d/%Y"),sum((D(r.get(k,"").strip() or "0") for k in ("G","H","I")),D(0)))
                        for r in audit.xrows(raw/"spy-distributions.xlsx") if r.get("B")=="SPY"),
      "IEF":audit.unique((audit.date(r[1],"%b %d, %Y"),D(r[3])) for r in sheets["Distributions"][1:])}
    result={"quality":"research_proxy","execution_date_kst":datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
            "issuer_manifest_sha256":audit.sha(audit_dir/"results.json"),"symbols":{}}
    for symbol in ("SPY","IEF"):
        p=yahoo/(symbol+".json")
        if audit.sha(p)!=audit.EXPECTED[symbol]:raise ValueError("Yahoo hash mismatch")
        data=json.loads(p.read_text(),parse_float=D)["chart"]["result"][0]
        if data.get("events",{}).get("splits"):raise ValueError("Split handling not supported")
        zone=ZoneInfo(data["meta"]["exchangeTimezoneName"])
        day=lambda t:datetime.fromtimestamp(t,zone).date().isoformat()
        dates=[day(t) for t in data["timestamp"]]
        close=data["indicators"]["quote"][0]["close"]
        adj=data["indicators"]["adjclose"][0]["adjclose"]
        if len(adj)!=len(dates) or any(v is None or not v.is_finite() or v<=0 for v in adj):
            raise ValueError("Missing/invalid adjusted close")
        if any(v is None for v in close):raise ValueError("Missing close")
        ydiv=audit.unique((day(e["date"]),D(str(e["amount"]))) for e in data["events"]["dividends"].values())
        od=official[symbol]
        yd={d:v for d,v in ydiv.items() if dates[0]<d<=dates[-1]}
        od={d:v for d,v in od.items() if dates[0]<d<=dates[-1]}
        if set(yd)!=set(od):raise ValueError("Distribution dates differ")
        series={
          "yahoo_adjclose":monthly(dates,adj),
          "yahoo_div_backward":monthly(dates,rebuild(dates,close,yd,"backward")),
          "issuer_div_backward":monthly(dates,rebuild(dates,close,od,"backward")),
          "issuer_div_ex_close":monthly(dates,rebuild(dates,close,od,"ex_close"))}
        pairs=[("yahoo_adjclose","yahoo_div_backward"),("yahoo_div_backward","issuer_div_backward"),
               ("issuer_div_backward","issuer_div_ex_close"),("yahoo_adjclose","issuer_div_ex_close")]
        comparisons={a+" -> "+b:compare(series[a],series[b]) for a,b in pairs}
        result["symbols"][symbol]={"source_sha256":audit.sha(p),"daily_rows":len(dates),
          "start":dates[0],"end":dates[-1],"events":len(od),"monthly_rows":len(series["yahoo_adjclose"]),
          "monthly_start":min(series["yahoo_adjclose"]),"monthly_end":max(series["yahoo_adjclose"]),
          "comparisons":comparisons,"monthly_returns":series}
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--raw",type=Path,required=True);p.add_argument("--yahoo",type=Path,required=True)
    p.add_argument("--audit-dir",type=Path,default=Path(__file__).resolve().parent.parent/"20261115-issuer-audit")
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();a.output.write_text(json.dumps(run(a.raw,a.yahoo,a.audit_dir),default=str,indent=2)+"\n")
