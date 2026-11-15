"""Issuer cross-check; standard library only. Inputs are private source files."""
import argparse, hashlib, json, re, zipfile
import xml.etree.ElementTree as E
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo

URLS = {
"spy-distributions.xlsx": "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx",
"spy-product.xlsx": "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-product-data-us-en.xlsx",
"ief-download": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239456&targetSite=us-ishares&userType=individual"}
EXPECTED = {"SPY": "3e83365a8d52cf1ffde81e712363da988ddbe03f87438713277d4abcb899ec85",
"IEF": "ee0b09bd18ecee55765b8a4d70f9085fc3c1a1e13d977ed3f13257505f267c56"}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def xrows(p):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(p) as z:
        strings = ["".join(t.text or "" for t in x.findall(".//s:t", ns))
                   for x in E.fromstring(z.read("xl/sharedStrings.xml"))]
        rows = []
        for row in E.fromstring(z.read("xl/worksheets/sheet1.xml")).findall(".//s:row", ns):
            out = {}
            for c in row:
                v = c.find("s:v", ns)
                if v is not None:
                    out[re.sub(r"\d", "", c.attrib["r"])] = strings[int(v.text)] if c.get("t") == "s" else v.text
            rows.append(out)
        return rows
def xml_sheets(p):
    # Issuer XML contains bare '&' in hyperlink attributes; repair only the
    # in-memory parser input. The downloaded bytes/hash remain unchanged.
    s = p.read_text()
    s, count = re.subn(r"&(?!#\d+;|#x[0-9a-fA-F]+;|amp;|lt;|gt;|quot;|apos;)", "&amp;", s)
    ns = {"s": "urn:schemas-microsoft-com:office:spreadsheet"}
    result = {}
    for sheet in E.fromstring(s).findall("s:Worksheet", ns):
        rows = []
        for row in sheet.findall("s:Table/s:Row", ns):
            cells = []
            for c in row.findall("s:Cell", ns):
                index = int(c.get("{"+ns["s"]+"}Index", len(cells)+1))
                cells.extend([""] * (index-1-len(cells)))
                data = c.find("s:Data", ns)
                cells.append("" if data is None else "".join(data.itertext()).strip())
            rows.append(cells)
        result[sheet.attrib["{"+ns["s"]+"}Name"]] = rows
    return result, count
def date(s, fmt): return datetime.strptime(s, fmt).date().isoformat()
def unique(rows):
    out = {}
    for day, amount in rows:
        if day in out: raise ValueError("duplicate issuer date: "+day)
        out[day] = amount
    return out
def compare(yahoo, official, start, end):
    y = {d:v for d,v in yahoo.items() if start <= d <= end}
    o = {d:v for d,v in official.items() if start <= d <= end}
    common = sorted(y.keys() & o.keys())
    diffs = {d:abs(y[d]-o[d]) for d in common}
    return {"start":start,"end":end,"yahoo_events":len(y),"issuer_events":len(o),
        "matched_dates":len(common),"yahoo_only_dates":sorted(y.keys()-o.keys()),
        "issuer_only_dates":sorted(o.keys()-y.keys()),
        "exact_amount_matches":sum(v == 0 for v in diffs.values()),
        "within_0_0005_usd":sum(v <= D("0.0005") for v in diffs.values()),
        "max_abs_amount_difference_usd":str(max(diffs.values(), default=D(0))),
        "outside_tolerance":[{"date":d,"yahoo":str(y[d]),"issuer":str(o[d])} for d in common if diffs[d]>D("0.0005")]}
def run(raw, yahoo_dir):
    sheets, repairs = xml_sheets(raw/"ief-download")
    official = {
        "SPY": unique((date(r["D"],"%m/%d/%Y"),sum((D(r.get(k,"").strip() or "0") for k in ("G","H","I")),D(0))) for r in xrows(raw/"spy-distributions.xlsx") if r.get("B")=="SPY"),
        "IEF": unique((date(r[1],"%b %d, %Y"),D(r[3])) for r in sheets["Distributions"][1:])}
    result={"retrieval_date_utc":"2026-11-15","quality":"research_proxy",
        "amount_tolerance_usd":"0.0005","historical_available_at_verified":False,
        "xml_bare_ampersands_repaired_in_memory":repairs,
        "issuer_sources":{name:{"url":url,"sha256":sha(raw/name)} for name,url in URLS.items()},
        "symbols":{}}
    for symbol in ("SPY","IEF"):
        p=yahoo_dir/(symbol+".json")
        if sha(p)!=EXPECTED[symbol]: raise ValueError("Original hash mismatch: "+symbol)
        data=json.loads(p.read_text(),parse_float=D)["chart"]["result"][0]
        zone=ZoneInfo(data["meta"]["exchangeTimezoneName"])
        day=lambda t: datetime.fromtimestamp(t,zone).date().isoformat()
        dates=[day(t) for t in data["timestamp"]]
        events=unique((day(v["date"]),D(str(v["amount"]))) for v in data["events"]["dividends"].values())
        o=official[symbol]
        result["symbols"][symbol]={"original_sha256":sha(p),"original_start":min(dates),"original_end":max(dates),
            "issuer_distribution_start":min(o),"issuer_distribution_end":max(o),
            "comparison":compare(events,o,min(dates),max(dates))}
    # NAV is a different observable: no equivalence test against exchange close.
    nav=sheets["Historical"]
    navdates=[date(r[0],"%b %d, %Y") for r in nav[1:] if r and r[0]]
    result["ief_historical"]={"field_names":nav[0],"rows":len(navdates),"start":min(navdates),"end":max(navdates),
        "exchange_close_verification":"not_performed_NAV_is_not_exchange_close"}
    result["spy_product"]={"date":[r["A"] for r in xrows(raw/"spy-product.xlsx") if r.get("B")=="SPY"][0],
        "exchange_close_verification":"not_performed_latest_snapshot_outside_original_period"}
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--raw",type=Path,required=True)
    p.add_argument("--yahoo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.write_text(json.dumps(run(a.raw,a.yahoo),indent=2,ensure_ascii=False)+"\n")
