#!/usr/bin/env python3
"""DART 전자공시 재무 데이터 도구 — 금융감독원 OpenAPI 기반, 외부 종속성 없음(stdlib만).

한국 상장사(KOSPI/KOSDAQ)의 **원본 공시 재무제표**를 DART OpenAPI에서 직접 가져온다.
financial-data 규범에서 한국 주식의 1순위(주) 출처가 DART인데, 기존 도구는
Yahoo/네이버(부 출처)만 다뤘다. 이 도구가 1차 자료(주 출처) 자동 수집을 담당한다.

- 연결(CFS) 기준 손익·재무상태·현금흐름 핵심 계정을 최근 3개년 비교표로 출력
- 단일 fnlttSinglAcntAll 호출이 당기/전기/전전기 3개년을 함께 반환하므로 1회 호출로 3년 확보
- 교차 검증은 tools/global_stock_data.py 의 네이버 섹션(부 출처)과 병행

사전 준비:
    opendart.fss.or.kr 에서 무료 API 키 발급(일 20,000건 한도) 후 환경변수 설정
    export DART_API_KEY=발급받은40자리키

사용법:
    python3 tools/dart_data.py financials 005930                       # 최근 사업보고서 연결 재무(3개년)
    python3 tools/dart_data.py financials 005930 --year 2024           # 특정 연도
    python3 tools/dart_data.py financials 005930 --report 11014        # 3분기 보고서
    python3 tools/dart_data.py financials 005930 --fs OFS              # 개별(별도) 재무
    python3 tools/dart_data.py company 005930                          # 기업개황
    python3 tools/dart_data.py disclosures 005930                      # 최근 공시 목록
    python3 tools/dart_data.py resolve 005930                          # 종목코드→corp_code 확인

보고서 코드(reprt_code): 11011 사업보고서(연간, 기본) / 11012 반기 / 11013 1분기 / 11014 3분기
재무 구분(fs_div): CFS 연결(기본) / OFS 개별(별도)

필요 Python >= 3.8, 외부 종속성 없음.
"""

import argparse
import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import date
from urllib.parse import urlencode
from xml.etree import ElementTree

_TIMEOUT = 30
_BASE = "https://opendart.fss.or.kr/api"
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
_CORPCODE_CACHE = os.path.join(_CACHE_DIR, "dart_corpcode.json")

# 보고서 코드 → 사람이 읽는 이름
_REPORT_NAMES = {
    "11011": "사업보고서(연간)",
    "11012": "반기보고서",
    "11013": "1분기보고서",
    "11014": "3분기보고서",
}

# 핵심 계정 추출용 후보 이름(공시마다 표기가 조금씩 달라 정규화 후 매칭)
# key: 표시 라벨, value: (재무제표구분 sj_div 집합, 계정명 후보 집합)
_KEY_ACCOUNTS = [
    ("매출액",       {"IS", "CIS"}, {"매출액", "수익(매출액)", "영업수익", "매출", "수익"}),
    ("영업이익",     {"IS", "CIS"}, {"영업이익", "영업이익(손실)", "영업손익"}),
    ("당기순이익",   {"IS", "CIS"}, {"당기순이익", "당기순이익(손실)", "분기순이익",
                                    "반기순이익", "연결당기순이익"}),
    ("자산총계",     {"BS"},        {"자산총계"}),
    ("부채총계",     {"BS"},        {"부채총계"}),
    ("자본총계",     {"BS"},        {"자본총계", "자본과부채총계"}),
    ("영업활동현금흐름", {"CF"},    {"영업활동현금흐름", "영업활동으로인한현금흐름",
                                    "영업활동순현금흐름"}),
]


def _die(msg: str, code: int = 1):
    print(msg)
    sys.exit(code)


def _api_key() -> str:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        _die(
            "❌ DART API 키가 없습니다.\n"
            "   opendart.fss.or.kr 에서 무료로 발급(가입 → 인증키 신청, 즉시 발급)한 뒤\n"
            "   환경변수로 설정하세요:\n"
            "       export DART_API_KEY=발급받은40자리키\n"
            "   (키는 코드·저장소에 저장하지 말고 환경변수로만 다룹니다.)"
        )
    return key


def _curl(url: str, binary: bool = False):
    """curl로 직접 요청(시스템 프록시 설정을 그대로 따른다). 다른 tools/ 스크립트와 동일 패턴."""
    result = subprocess.run(
        ["curl", "-s",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         url],
        capture_output=True, timeout=_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"요청 실패: {url.split('?')[0]}")
    return result.stdout if binary else result.stdout.decode("utf-8")


def _api_json(endpoint: str, params: dict) -> dict:
    params = dict(params, crtfc_key=_api_key())
    url = f"{_BASE}/{endpoint}?{urlencode(params)}"
    data = json.loads(_curl(url))
    status = data.get("status")
    # DART 상태코드: 000 정상, 013 데이터 없음, 그 외 오류
    if status and status not in ("000", "013"):
        raise RuntimeError(f"DART API 오류 [{status}] {data.get('message', '')}")
    return data


# ---------------------------------------------------------------------------
# corp_code 매핑(종목코드 6자리 → DART 고유 corp_code 8자리)
# ---------------------------------------------------------------------------

def _load_corpcode_map() -> dict:
    """corpCode.xml(ZIP)을 받아 {종목코드: {corp_code, corp_name}} 매핑을 만들고 캐싱한다."""
    if os.path.exists(_CORPCODE_CACHE):
        try:
            with open(_CORPCODE_CACHE, encoding="utf-8") as f:
                cached = json.load(f)
            if cached:
                return cached
        except (ValueError, OSError):
            pass  # 캐시 손상 시 재다운로드

    url = f"{_BASE}/corpCode.xml?{urlencode({'crtfc_key': _api_key()})}"
    raw = _curl(url, binary=True)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml_bytes = zf.read(zf.namelist()[0])
    except (zipfile.BadZipFile, IndexError):
        # ZIP이 아니면 오류 응답(대개 API 키 문제)이 XML/JSON으로 옴
        raise RuntimeError(
            "corpCode 다운로드 실패 — API 키가 유효한지 확인하세요. "
            f"응답 앞부분: {raw[:200]!r}")

    root = ElementTree.fromstring(xml_bytes)
    mapping = {}
    for el in root.iter("list"):
        stock_code = (el.findtext("stock_code") or "").strip()
        if not stock_code or stock_code == " ":
            continue  # 상장사만(비상장은 stock_code 공란)
        mapping[stock_code] = {
            "corp_code": (el.findtext("corp_code") or "").strip(),
            "corp_name": (el.findtext("corp_name") or "").strip(),
        }

    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_CORPCODE_CACHE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)
    return mapping


def _resolve(code: str):
    """6자리 종목코드 → (corp_code, corp_name). 못 찾으면 (None, None)."""
    code6 = code.strip().split(".")[0].zfill(6)
    mapping = _load_corpcode_map()
    info = mapping.get(code6)
    if not info:
        return None, None
    return info["corp_code"], info["corp_name"]


# ---------------------------------------------------------------------------
# 포맷 헬퍼
# ---------------------------------------------------------------------------

def _parse_amount(s):
    """DART 금액 문자열('1,234,567' / '-' / '') → float(원). 파싱 실패 시 None."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_krw(value) -> str:
    """원 단위 → 조/억 표기."""
    if value is None:
        return "-"
    v = float(value)
    if abs(v) >= 1e12:
        return f"{v / 1e12:,.2f}조원"
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.1f}억원"
    return f"{v:,.0f}원"


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):+.1f}%"


def _norm(name: str) -> str:
    """계정명 정규화: 공백·괄호 제거로 표기 차이 흡수."""
    return (name or "").replace(" ", "").replace("(", "").replace(")", "")


# ---------------------------------------------------------------------------
# 명령 구현
# ---------------------------------------------------------------------------

def cmd_resolve(code: str):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")
    print(f"종목코드 {code.zfill(6)} → corp_code {corp_code} ({corp_name})")


def _extract_accounts(items, fs_div):
    """fnlttSinglAcntAll 응답 항목 리스트에서 핵심 계정의 3개년 값을 뽑는다.

    반환: {라벨: {"thstrm": v, "frmtrm": v, "bfefrmtrm": v}}
    """
    result = {}
    for label, sj_set, name_cands in _KEY_ACCOUNTS:
        norm_cands = {_norm(n) for n in name_cands}
        for it in items:
            if it.get("sj_div") not in sj_set:
                continue
            if _norm(it.get("account_nm", "")) not in norm_cands:
                continue
            result[label] = {
                "thstrm": _parse_amount(it.get("thstrm_amount")),
                "frmtrm": _parse_amount(it.get("frmtrm_amount")),
                "bfefrmtrm": _parse_amount(it.get("bfefrmtrm_amount")),
            }
            break  # 첫 매칭만 사용(표준 계정이 먼저 옴)
    return result


def _fetch_financials(corp_code, year, reprt_code, fs_div):
    data = _api_json("fnlttSinglAcntAll.json", {
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": reprt_code,
        "fs_div": fs_div,
    })
    if data.get("status") == "013":
        return None
    return data.get("list") or None


def cmd_financials(code: str, year=None, reprt_code="11011", fs_div="CFS"):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")

    # 연도 미지정 시: 직전 회계연도부터 시도, 없으면 한 해 더 과거로
    try_years = [year] if year else [date.today().year - 1, date.today().year - 2]

    items = None
    used_year = None
    used_fs = fs_div
    for y in try_years:
        items = _fetch_financials(corp_code, y, reprt_code, fs_div)
        if items:
            used_year = y
            break
    # 연결(CFS)이 비면 개별(OFS)로 자동 폴백(연결재무제표 미작성 기업 대응)
    if not items and fs_div == "CFS":
        for y in try_years:
            items = _fetch_financials(corp_code, y, reprt_code, "OFS")
            if items:
                used_year, used_fs = y, "OFS"
                break

    if not items:
        _die(f"⚠️ {corp_name}({code}) 의 재무 데이터를 얻지 못했습니다 "
             f"(연도 {try_years}, 보고서 {reprt_code}). "
             f"--year 로 연도를 지정하거나 dart.fss.or.kr 에서 확인하세요.")

    accounts = _extract_accounts(items, used_fs)

    fs_label = "연결(CFS)" if used_fs == "CFS" else "개별/별도(OFS)"
    y0, y1, y2 = used_year, used_year - 1, used_year - 2

    print("=" * 64)
    print(f"DART 재무제표: {corp_name} ({code.zfill(6)}) — {fs_label}")
    print(f"기준: {used_year}년 {_REPORT_NAMES.get(reprt_code, reprt_code)}  "
          f"| corp_code {corp_code}")
    print("=" * 64)
    print(f"  {'계정':<18}{y2:>14}{y1:>14}{y0:>14}")
    print("  " + "-" * 58)

    order = ["매출액", "영업이익", "당기순이익",
             "자산총계", "부채총계", "자본총계", "영업활동현금흐름"]
    for label in order:
        a = accounts.get(label)
        if not a:
            print(f"  {label:<18}{'-':>14}{'-':>14}{'-':>14}")
            continue
        print(f"  {label:<18}"
              f"{_fmt_krw(a['bfefrmtrm']):>14}"
              f"{_fmt_krw(a['frmtrm']):>14}"
              f"{_fmt_krw(a['thstrm']):>14}")

    # 파생 지표(당기 기준)
    rev = accounts.get("매출액", {})
    op = accounts.get("영업이익", {})
    ni = accounts.get("당기순이익", {})
    eq = accounts.get("자본총계", {})
    li = accounts.get("부채총계", {})

    print("\n  [파생 지표 — 당기 기준]")
    if rev.get("thstrm") and op.get("thstrm") is not None:
        print(f"  영업이익률:        {_fmt_pct(op['thstrm'] / rev['thstrm'] * 100)}")
    if rev.get("thstrm") and ni.get("thstrm") is not None:
        print(f"  순이익률:          {_fmt_pct(ni['thstrm'] / rev['thstrm'] * 100)}")
    if eq.get("thstrm") and ni.get("thstrm") is not None:
        print(f"  ROE(기말자본):     {_fmt_pct(ni['thstrm'] / eq['thstrm'] * 100)} "
              f"(단순: 순이익/기말 자기자본)")
    if eq.get("thstrm") and li.get("thstrm") is not None:
        print(f"  부채비율:          {_fmt_pct(li['thstrm'] / eq['thstrm'] * 100)} "
              f"(부채총계/자본총계)")
    if rev.get("thstrm") and rev.get("frmtrm"):
        print(f"  매출 성장률:       {_fmt_pct((rev['thstrm'] / rev['frmtrm'] - 1) * 100)}")

    print("\n  출처: DART 전자공시(opendart.fss.or.kr) — 1차 공시 원본(주 출처).")
    print("  교차 검증: python3 tools/global_stock_data.py financials "
          f"{code.zfill(6)} (네이버·Yahoo, 부 출처). 오차 >1% 시 표기.")


def cmd_company(code: str):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")
    data = _api_json("company.json", {"corp_code": corp_code})
    if data.get("status") == "013":
        _die(f"⚠️ {corp_name}({code}) 기업개황 데이터가 없습니다.")

    print("=" * 64)
    print(f"기업개황: {data.get('corp_name', corp_name)} ({code.zfill(6)})")
    print("=" * 64)
    fields = [
        ("정식 명칭", "corp_name"), ("영문 명칭", "corp_name_eng"),
        ("대표자", "ceo_nm"), ("법인구분", "corp_cls"),
        ("설립일", "est_dt"), ("업종코드", "induty_code"),
        ("결산월", "acc_mt"), ("홈페이지", "hm_url"),
        ("주소", "adres"),
    ]
    for label, key in fields:
        val = (data.get(key) or "").strip()
        if val:
            print(f"  {label:<10} {val}")
    print(f"\n  corp_code: {corp_code}")


def cmd_disclosures(code: str, count=15):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")
    data = _api_json("list.json", {
        "corp_code": corp_code,
        "page_count": str(count),
        "last_reprt_at": "Y",  # 최종보고서 기준
    })
    disclosures = data.get("list") or []
    if not disclosures:
        _die(f"⚠️ {corp_name}({code}) 최근 공시가 없습니다.")

    print("=" * 64)
    print(f"최근 공시 목록: {corp_name} ({code.zfill(6)})")
    print("=" * 64)
    for d in disclosures[:count]:
        rcept_no = d.get("rcept_no", "")
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        print(f"  [{d.get('rcept_dt', '')}] {d.get('report_nm', '')}")
        print(f"      제출인:{d.get('flr_nm', '')}  접수번호:{rcept_no}")
        print(f"      {url}")


def main():
    p = argparse.ArgumentParser(
        description="DART 전자공시 재무 데이터 도구(한국 상장사, 주 출처).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("financials", help="핵심 재무제표(연결 우선, 3개년)")
    pf.add_argument("code", help="종목코드 6자리(예: 005930)")
    pf.add_argument("--year", type=int, default=None, help="사업연도(미지정 시 직전연도)")
    pf.add_argument("--report", default="11011",
                    help="보고서코드 11011 사업(기본)/11012 반기/11013 1Q/11014 3Q")
    pf.add_argument("--fs", default="CFS", choices=["CFS", "OFS"],
                    help="CFS 연결(기본)/OFS 개별")

    pc = sub.add_parser("company", help="기업개황")
    pc.add_argument("code")

    pd = sub.add_parser("disclosures", help="최근 공시 목록")
    pd.add_argument("code")
    pd.add_argument("--count", type=int, default=15)

    pr = sub.add_parser("resolve", help="종목코드 → corp_code 확인")
    pr.add_argument("code")

    args = p.parse_args()
    try:
        if args.cmd == "financials":
            cmd_financials(args.code, args.year, args.report, args.fs)
        elif args.cmd == "company":
            cmd_company(args.code)
        elif args.cmd == "disclosures":
            cmd_disclosures(args.code, args.count)
        elif args.cmd == "resolve":
            cmd_resolve(args.code)
    except (ConnectionError, RuntimeError) as e:
        _die(f"❌ {e}")


if __name__ == "__main__":
    main()
