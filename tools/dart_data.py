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
    python3 tools/dart_data.py financials 005930 --as-of 2025-03-31    # 2025-03-31까지 접수된 최신 사업보고서
    python3 tools/dart_data.py disclosures 005930 --as-of 2025-03-31   # 그날까지 접수된 공시(정정 전 원공시 포함)
    python3 tools/dart_data.py resolve 005930                          # 종목코드→corp_code 확인

보고서 코드(reprt_code): 11011 사업보고서(연간, 기본) / 11012 반기 / 11013 1분기 / 11014 3분기
재무 구분(fs_div): CFS 연결(기본) / OFS 개별(별도)

시점 통제(--as-of YYYY-MM-DD):
  공시 목록의 접수일(rcept_dt)로 그 날짜까지 접수된 정기보고서만 고른다(사업연도 종료 직후처럼
  아직 공시 전인 기간의 수치를 쓰지 않게). 재무 API는 정정공시가 있으면 정정 후 값을 돌려주는데,
  돌려준 값의 접수번호(rcept_no) 날짜가 --as-of 보다 늦으면 '그 시점에 공개돼 있던 값'이 아니므로
  수치를 내주지 않고 보류한다(종료 코드 5, 원공시 문서 링크 안내).
  설계 출처: TradingAgents(Apache 2.0)의 SEC EDGAR 공시일 기준 시점 통제를 DART에 맞게 적용.

필요 Python >= 3.8, 외부 종속성 없음.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from xml.etree import ElementTree

_TIMEOUT = 30
_TIMEOUT_BULK = 300  # corpCode.xml(약 3.5MB ZIP)은 다운로드가 오래 걸려 별도 타임아웃
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

# 핵심 계정 추출 규칙.
# value: (재무제표구분 sj_div 집합, XBRL account_id 후보 집합, 계정명 후보 집합)
# 매칭 우선순위: account_id 집합이 비어있지 않으면 account_id로만 매칭(계정명 무시),
# 비어있으면 정규화한 계정명으로 매칭. IFRS 표준 account_id는 표기 차이·중복에 강하다.
#
# 지배주주순이익이 특히 중요: 한국 기업 다수가 별도 손익계산서(IS) 없이 단일
# 포괄손익계산서(CIS)만 제출하는데, 이때 CIS 안에 '지배기업의 소유주지분'이
# 순이익 귀속분과 포괄손익 귀속분 두 번 나온다. 계정명은 같지만 account_id는
# 순이익=ifrs-full_ProfitLossAttributableToOwnersOfParent,
# 포괄손익=ifrs-full_ComprehensiveIncomeAttributableToOwnersOfParent 로 구분되므로
# account_id로만 매칭해 포괄손익 오매칭을 원천 차단한다.
_KEY_ACCOUNTS = [
    ("매출액",       {"IS", "CIS"}, set(),
        {"매출액", "수익(매출액)", "영업수익", "매출", "수익"}),
    ("영업이익",     {"IS", "CIS"}, set(),
        {"영업이익", "영업이익(손실)", "영업손익"}),
    ("당기순이익",   {"IS", "CIS"}, {"ifrs-full_ProfitLoss"},
        {"당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익", "연결당기순이익"}),
    ("지배주주순이익", {"IS", "CIS"}, {"ifrs-full_ProfitLossAttributableToOwnersOfParent"},
        set()),
    ("자산총계",     {"BS"},        set(), {"자산총계"}),
    ("부채총계",     {"BS"},        set(), {"부채총계"}),
    ("자본총계",     {"BS"},        set(), {"자본총계", "자본과부채총계"}),
    ("영업활동현금흐름", {"CF"},    set(),
        {"영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동순현금흐름"}),
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


def _curl(url: str, binary: bool = False, timeout: int = _TIMEOUT):
    """curl로 직접 요청(시스템 프록시 설정을 그대로 따른다). 다른 tools/ 스크립트와 동일 패턴."""
    try:
        result = subprocess.run(
            ["curl", "-sS", "-L", "--retry", "2",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             url],
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ConnectionError(f"요청 시간 초과({timeout}s): {url.split('?')[0]}")
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

    # corpCode.xml(ZIP)은 약 3.5MB로, subprocess stdout 파이프로 받으면 매우 느리다.
    # curl -o 로 파일에 직접 저장하는 편이 빠르고 안정적이다.
    os.makedirs(_CACHE_DIR, exist_ok=True)
    zip_path = os.path.join(_CACHE_DIR, "dart_corpcode.zip")
    url = f"{_BASE}/corpCode.xml?{urlencode({'crtfc_key': _api_key()})}"
    try:
        result = subprocess.run(
            ["curl", "-sS", "-L", "--retry", "2", "-o", zip_path,
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             url],
            capture_output=True, timeout=_TIMEOUT_BULK,
        )
    except subprocess.TimeoutExpired:
        raise ConnectionError(f"corpCode 다운로드 시간 초과({_TIMEOUT_BULK}s)")
    if result.returncode != 0 or not os.path.exists(zip_path):
        raise ConnectionError("corpCode 다운로드 실패 — 네트워크/프록시를 확인하세요.")

    try:
        with zipfile.ZipFile(zip_path) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
    except (zipfile.BadZipFile, IndexError):
        # ZIP이 아니면 오류 응답(대개 API 키 문제)이 XML/JSON으로 옴
        with open(zip_path, "rb") as f:
            head = f.read(200)
        raise RuntimeError(
            "corpCode 다운로드 실패 — API 키가 유효한지 확인하세요. "
            f"응답 앞부분: {head!r}")

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
    """계정명 정규화: 공백·괄호 제거로 표기 차이 흡수.

    str.split()는 일반 공백뿐 아니라 non-breaking space(\\xa0) 등
    DART 공시 렌더링 과정에서 섞이는 모든 공백 문자를 제거한다.
    """
    return "".join((name or "").split()).replace("(", "").replace(")", "")


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
    for label, sj_set, id_cands, name_cands in _KEY_ACCOUNTS:
        norm_cands = {_norm(n) for n in name_cands}
        match = None
        # 1순위: XBRL account_id (지정된 경우). 표기 차이·계정명 중복에 가장 강하다.
        if id_cands:
            for it in items:
                if it.get("sj_div") in sj_set and it.get("account_id") in id_cands:
                    match = it
                    break
        # 2순위: 계정명 폴백. id 매칭이 실패했고 계정명 후보가 있을 때만 시도한다.
        #   → 구형·비표준 공시(account_id 누락)도 계정명으로 잡을 수 있다.
        #   지배주주순이익은 name_cands를 비워둬 폴백을 막는다(CIS 계정명 중복 오매칭 방지).
        if match is None and norm_cands:
            for it in items:
                if (it.get("sj_div") in sj_set
                        and _norm(it.get("account_nm", "")) in norm_cands):
                    match = it
                    break
        if match is not None:
            result[label] = {
                "thstrm": _parse_amount(match.get("thstrm_amount")),
                "frmtrm": _parse_amount(match.get("frmtrm_amount")),
                "bfefrmtrm": _parse_amount(match.get("bfefrmtrm_amount")),
            }
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


# ---------------------------------------------------------------------------
# 시점 통제(--as-of)
# ---------------------------------------------------------------------------

_PERIODIC_RE = re.compile(r"(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)")
# 결산월 이후 경과 개월 → 보고서 코드
_CODE_BY_OFFSET = {0: "11011", 3: "11013", 6: "11012", 9: "11014"}


def _withheld(reason: str, alternative: str = ""):
    """tools/_us_common.py 와 같은 WITHHELD 규칙(종료 코드 5)."""
    print(f"WITHHELD: {reason}")
    if alternative:
        print(f"  대안: {alternative}")
    print("  이 데이터를 추정하거나 현재 값으로 대신 채우지 마세요.")
    sys.exit(5)


def report_code_of(report_nm: str, acc_mt: int):
    """정기보고서 이름 → (보고서 코드, 기간 연도, 기간 월). 정기보고서가 아니면 None.

    '[기재정정]사업보고서 (2024.12)' 처럼 정정 접두어가 붙어도 같은 기간으로 읽는다.
    분기 구분은 결산월 기준 경과 개월로 정한다(12월 결산: 3월=1분기, 6월=반기, 9월=3분기).
    """
    m = _PERIODIC_RE.search(report_nm or "")
    if not m:
        return None
    kind, y, mo = m.group(1), int(m.group(2)), int(m.group(3))
    offset = (mo - acc_mt) % 12
    code = {"사업": "11011", "반기": "11012"}.get(kind) or _CODE_BY_OFFSET.get(offset)
    if code is None:
        return None
    return code, y, mo


def periodic_reports_as_of(corp_code: str, as_of: str, acc_mt: int, years_back: int = 4) -> list:
    """as_of 까지 접수된 정기보고서 [(접수일, 접수번호, 보고서명, 코드, 기간연도)] — 최신 접수순.

    last_reprt_at=N: 정정 전 원공시도 포함해야 '그 시점에 무엇이 공개돼 있었나'를 알 수 있다.
    """
    end = datetime.strptime(as_of, "%Y-%m-%d")
    params = {
        "corp_code": corp_code,
        "bgn_de": (end - timedelta(days=365 * years_back)).strftime("%Y%m%d"),
        "end_de": end.strftime("%Y%m%d"),
        "pblntf_ty": "A",          # 정기공시
        "last_reprt_at": "N",
        "page_count": "100",
    }
    rows, page = [], 1
    while True:
        data = _api_json("list.json", dict(params, page_no=str(page)))
        for d in data.get("list") or []:
            parsed = report_code_of(d.get("report_nm", ""), acc_mt)
            if parsed and d.get("rcept_dt", "") <= end.strftime("%Y%m%d"):
                rows.append((d["rcept_dt"], d["rcept_no"], d["report_nm"], parsed[0], parsed[1]))
        if page >= int(data.get("total_page") or 1):
            break
        page += 1
    return sorted(rows, reverse=True)


def _acc_month(corp_code: str) -> int:
    """결산월(기업개황 acc_mt). 조회 실패 시 12월로 본다."""
    try:
        return int(_api_json("company.json", {"corp_code": corp_code}).get("acc_mt") or 12)
    except (ValueError, RuntimeError, ConnectionError):
        return 12


def share_counts(corp_code: str, as_of: str = None):
    """as_of 까지 접수된 가장 최근 정기보고서의 주식 총수(보통주·우선주 구분). 없으면 None.

    반환: {"보통주"/"우선주": {"발행": n, "자기주식": n, "유통": n}, "기준일", "보고서", "접수번호"}
    DART는 우선주를 종류(우, 2우B 등)와 무관하게 한 줄로 합산해 준다.
    """
    as_of = as_of or date.today().strftime("%Y-%m-%d")
    acc_mt = _acc_month(corp_code)
    for rcept_dt, rcept_no, report_nm, reprt_code, period_year in \
            periodic_reports_as_of(corp_code, as_of, acc_mt, years_back=2):
        # 12월 결산 외에는 사업연도 표기가 회사마다 달라 두 해를 시도하고 접수번호로 맞는 쪽을 확인한다.
        for y in ([period_year] if acc_mt == 12 else [period_year, period_year - 1]):
            data = _api_json("stockTotqySttus.json",
                             {"corp_code": corp_code, "bsns_year": str(y), "reprt_code": reprt_code})
            rows = {r.get("se"): r for r in data.get("list") or [] if r.get("rcept_no") == rcept_no}
            if "보통주" not in rows:
                continue
            out = {"기준일": rows["보통주"].get("stlm_dt", ""), "보고서": report_nm, "접수번호": rcept_no}
            for se in ("보통주", "우선주"):
                r = rows.get(se) or {}
                issued = _parse_amount(r.get("istc_totqy")) or 0.0
                treasury = _parse_amount(r.get("tesstk_co")) or 0.0
                out[se] = {"발행": issued, "자기주식": treasury,
                           "유통": _parse_amount(r.get("distb_stock_co")) or issued - treasury}
            return out
    return None


def _financials_as_of(corp_code, corp_name, code, as_of, year, reprt_code, fs_div):
    """as_of 시점 기준 재무 → (항목, 사업연도, 재무구분, 기준 보고서 튜플)."""
    acc_mt = _acc_month(corp_code)
    reports = [r for r in periodic_reports_as_of(corp_code, as_of, acc_mt)
               if r[3] == reprt_code and (year is None or r[4] in (year, year + 1))]
    if not reports:
        _die(f"NO_DATA: {corp_name}({code}) 의 {_REPORT_NAMES.get(reprt_code, reprt_code)}가 "
             f"{as_of} 까지 접수된 것이 없습니다.", 3)
    # 가장 최근 기간을 고르고, 그 기간의 공시(원공시 + as_of 이전 정정) 중 가장 늦은 것을 기준으로 삼는다.
    period_year = max(r[4] for r in reports)
    same_period = [r for r in reports if r[4] == period_year]
    chosen = same_period[0]                     # 최신 접수(정정이 있으면 정정)
    earliest = min(r[1] for r in same_period)   # 원공시 접수번호
    rcept_dt, rcept_no, report_nm, _, _ = chosen
    # 12월 결산은 기간 연도 = 사업연도. 그 외 결산월은 사업연도 표기가 회사마다 달라 두 해를 시도하고,
    # 응답의 접수번호가 고른 보고서(또는 그 정정)인지로 맞는 쪽을 확인한다.
    candidates = [year] if year else ([period_year] if acc_mt == 12 else [period_year, period_year - 1])
    for fs in ([fs_div, "OFS"] if fs_div == "CFS" else [fs_div]):
        for y in candidates:
            items = _fetch_financials(corp_code, y, reprt_code, fs)
            if not items:
                continue
            served = max((it.get("rcept_no", "") for it in items), default="")
            if served and served < earliest:
                continue  # 이 기간 원공시보다 이른 보고서의 값 → 사업연도 추정이 틀림
            if served[:8] > as_of.replace("-", ""):
                _withheld(
                    f"{corp_name}({code}) {report_nm}: DART 재무 API가 {served[:8]} 접수 정정공시 값을 "
                    f"돌려줘 {as_of} 시점에 공개돼 있던 값이 아닙니다.",
                    f"그 시점 공시 문서를 직접 확인: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}")
            return items, y, fs, chosen + (served,)
    _die(f"NO_DATA: {corp_name}({code}) {report_nm}(접수 {rcept_dt}) 의 재무 데이터를 API에서 얻지 못했습니다.", 3)


def cmd_financials(code: str, year=None, reprt_code="11011", fs_div="CFS", as_of=None):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")

    if as_of and as_of < date.today().strftime("%Y-%m-%d"):
        items, used_year, used_fs, basis = _financials_as_of(
            corp_code, corp_name, code, as_of, year, reprt_code, fs_div)
        _print_financials(code, corp_name, corp_code, items, used_year, reprt_code, used_fs,
                          f"시점: {as_of} 까지 접수된 공시 기준 — {basis[2]} (접수 {basis[0]}) "
                          f"| 값의 접수번호 {basis[5]}")
        return

    # 연도 미지정 시: 당해연도 → 직전연도 → 전전연도 순으로 시도.
    # 당해연도 분기·반기 보고서(11013/11012/11014)를 우선 잡고,
    # 아직 미공시인 당해연도 연간보고서(11011)는 013(데이터 없음)이 와서 자연 폴백된다.
    try_years = ([year] if year
                 else [date.today().year, date.today().year - 1, date.today().year - 2])

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

    _print_financials(code, corp_name, corp_code, items, used_year, reprt_code, used_fs)


def _print_financials(code, corp_name, corp_code, items, used_year, reprt_code, used_fs, basis_line=""):
    accounts = _extract_accounts(items, used_fs)

    fs_label = "연결(CFS)" if used_fs == "CFS" else "개별/별도(OFS)"
    y0, y1, y2 = used_year, used_year - 1, used_year - 2

    print("=" * 64)
    print(f"DART 재무제표: {corp_name} ({code.zfill(6)}) — {fs_label}")
    print(f"기준: {used_year}년 {_REPORT_NAMES.get(reprt_code, reprt_code)}  "
          f"| corp_code {corp_code}")
    if basis_line:
        print(basis_line)
    print("=" * 64)
    print(f"  {'계정':<18}{y2:>14}{y1:>14}{y0:>14}")
    print("  " + "-" * 58)

    order = ["매출액", "영업이익", "당기순이익", "지배주주순이익",
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


def cmd_disclosures(code: str, count=15, as_of=None):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")
    # bgn_de(시작일) 미지정 시 DART는 '당일 접수 공시'만 반환하므로,
    # 기준일로부터 1년치를 조회하도록 시작일을 1년 전으로 지정한다.
    end = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else date.today()
    historical = end < date.today()
    data = _api_json("list.json", {
        "corp_code": corp_code,
        "bgn_de": (end - timedelta(days=365)).strftime("%Y%m%d"),
        "end_de": end.strftime("%Y%m%d"),
        "page_count": str(count),
        # 최종보고서 기준. 과거 시점이면 정정 전 원공시도 보여야 그때 공개돼 있던 것을 안다.
        "last_reprt_at": "N" if historical else "Y",
    })
    disclosures = data.get("list") or []
    if not disclosures:
        _die(f"⚠️ {corp_name}({code}) 최근 공시가 없습니다.")

    print("=" * 64)
    print(f"최근 공시 목록: {corp_name} ({code.zfill(6)})"
          + (f" — {end} 까지 접수, 정정 전 원공시 포함" if historical else ""))
    print("=" * 64)
    for d in disclosures[:count]:
        rcept_no = d.get("rcept_no", "")
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        print(f"  [{d.get('rcept_dt', '')}] {d.get('report_nm', '')}")
        print(f"      제출인:{d.get('flr_nm', '')}  접수번호:{rcept_no}")
        print(f"      {url}")


def _as_of(value: str):
    """--as-of 를 YYYY-MM-DD로 정규화하고 미래 날짜는 오늘로 자른다. 비어 있으면 None."""
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        _die(f"❌ --as-of 형식 오류: {value} (YYYY-MM-DD)")
    return min(d, date.today()).strftime("%Y-%m-%d")


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
    pf.add_argument("--as-of", default="", help="이 날짜까지 접수된 공시 기준(YYYY-MM-DD, 기본 오늘)")

    pc = sub.add_parser("company", help="기업개황")
    pc.add_argument("code")

    pd = sub.add_parser("disclosures", help="최근 공시 목록")
    pd.add_argument("code")
    pd.add_argument("--count", type=int, default=15)
    pd.add_argument("--as-of", default="", help="이 날짜까지 접수된 공시(YYYY-MM-DD)")

    pr = sub.add_parser("resolve", help="종목코드 → corp_code 확인")
    pr.add_argument("code")

    args = p.parse_args()
    try:
        if args.cmd == "financials":
            cmd_financials(args.code, args.year, args.report, args.fs, _as_of(args.as_of))
        elif args.cmd == "company":
            cmd_company(args.code)
        elif args.cmd == "disclosures":
            cmd_disclosures(args.code, args.count, _as_of(args.as_of))
        elif args.cmd == "resolve":
            cmd_resolve(args.code)
    except (ConnectionError, RuntimeError) as e:
        _die(f"❌ {e}")


if __name__ == "__main__":
    main()
