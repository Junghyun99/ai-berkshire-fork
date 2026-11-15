"""Single-event adjustment diagnostic, not a replacement return dataset."""
import argparse, hashlib, json
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo
EXPECTED="3e83365a8d52cf1ffde81e712363da988ddbe03f87438713277d4abcb899ec85"
OFFICIAL=D("1.636431")  # EDINET S100NQRF p43; current issuer XLSX agrees.
def diagnostic(c0,c1,a0,a1,dividend):
    if min(c0,c1,a0,a1)<=0: raise ValueError("Prices must be positive")
    k0,k1=a0/c0,a1/c1
    implied=c0*(1-k0/k1)
    base=a1/a0
    candidate=(c1/c0)/(1-dividend/c0)
    return {"implied_dividend_usd":implied,
            "observed_daily_return":base-1,
            "official_model_daily_return":candidate-1,
            "daily_return_difference_bp":(candidate-base)*10000,
            "conditional_wealth_ratio":candidate/base,
            "conditional_wealth_difference_bp":(candidate/base-1)*10000}
def run(p):
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if digest!=EXPECTED: raise ValueError("Original SPY hash mismatch")
    data=json.loads(p.read_text(),parse_float=D)["chart"]["result"][0]
    zone=ZoneInfo(data["meta"]["exchangeTimezoneName"])
    days=[datetime.fromtimestamp(t,zone).date().isoformat() for t in data["timestamp"]]
    i=days.index("2021-12-17")
    if days[i-1]!="2021-12-16": raise ValueError("Missing prior day")
    if data.get("events",{}).get("splits"): raise ValueError("Review split events before inference")
    q=data["indicators"]["quote"][0]["close"]
    a=data["indicators"]["adjclose"][0]["adjclose"]
    result=diagnostic(q[i-1],q[i],a[i-1],a[i],OFFICIAL)
    monthly={}
    for j,day in enumerate(days): monthly[day[:7]]=j
    dec,nov=monthly["2021-12"],monthly["2021-11"]
    gross=a[dec]/a[nov]
    result.update({"original_sha256":digest,"prior_date":days[i-1],"ex_date":days[i],
                   "prior_close":q[i-1],"ex_close":q[i],"prior_adjclose":a[i-1],"ex_adjclose":a[i],
                   "official_dividend":OFFICIAL,"yahoo_event_dividend":D("1.633"),
                   "december_observed_return":gross-1,
                   "december_conditional_return":gross*result["conditional_wealth_ratio"]-1,
                   "december_difference_bp":gross*(result["conditional_wealth_ratio"]-1)*10000,
                   "quality":"research_proxy","inference_model":"backward_factor = 1 - dividend/prior_close",
                   "causal_vendor_error_proven":False,"historical_available_at_verified":False})
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("source",type=Path);p.add_argument("output",type=Path)
    a=p.parse_args();a.output.write_text(json.dumps(run(a.source),default=str,indent=2)+"\n")
