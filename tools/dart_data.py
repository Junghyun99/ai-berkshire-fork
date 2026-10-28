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
    python3 tools/dart_data.py insiders 005930 --days 180              # 임원·주요주주 소유 보고(내부자 지분 변동)
    python3 tools/dart_data.py major-holders 005930 --days 365         # 5% 이상 대량보유 보고
    python3 tools/dart_data.py insiders 005930 --as-of 2025-06-30      # 그날까지 접수된 보고만

보고서 코드(reprt_code): 11011 사업보고서(연간, 기본) / 11012 반기 / 11013 1분기 / 11014 3분기
재무 구분(fs_div): CFS 연결(기본) / OFS 개별(별도)

시점 통제(--as-of YYYY-MM-DD):
  공시 목록의 접수일(rcept_dt)로 그 날짜까지 접수된 정기보고서만 고른다(사업연도 종료 직후처럼
  아직 공시 전인 기간의 수치를 쓰지 않게). 재무 API는 정정공시가 있으면 정정 후 값을 돌려주는데,
  돌려준 값의 접수번호(rcept_no) 날짜가 --as-of 보다 늦으면 '그 시점에 공개돼 있던 값'이 아니므로
  수치를 내주지 않고 보류한다(종료 코드 5, 원공시 문서 링크 안내).
  설계 출처: TradingAgents(Apache 2.0)의 SEC EDGAR 공시일 기준 시점 통제를 DART에 맞게 적용.
  insiders / major-holders 는 보고서 접수일(rcept_dt)로 자르므로 그 시점에 공개돼 있던 보고만 쓴다.

내부자·대량보유(insiders / major-holders):
  TradingAgents·Alpha Vantage 의 insider transactions 에 해당하는 한국 데이터.
  - insiders: '임원ㆍ주요주주 특정증권등 소유상황보고서'(elestock). 보고마다 직전 보고 대비 증감 주식수가 있다.
    증감 사유(장내매수·장내매도·주식보상·상속·증여 등)는 API에 없으므로 원문으로 확인해야 하고,
    증가를 '매수 신호'로 바로 읽지 않는다(대기업 임원 보고의 상당수는 주식보상).
  - major-holders: '주식등의 대량보유상황보고서'(majorstock, 5% 룰). 보고자의 지분율은 특별관계자 합산 기준.

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


def _api_json(endpoint: str, params: dict, timeout: int = _TIMEOUT) -> dict:
    params = dict(params, crtfc_key=_api_key())
    url = f"{_BASE}/{endpoint}?{urlencode(params)}"
    data = json.loads(_curl(url, timeout=timeout))
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


# ---------------------------------------------------------------------------
# 내부자(임원·주요주주) · 대량보유(5%)
# ---------------------------------------------------------------------------

_HOLDINGS_CACHE_TTL = 6 * 3600


def _holdings_rows(endpoint: str, corp_code: str) -> list:
    """elestock·majorstock 은 기간 인자 없이 전체 이력을 돌려준다(대기업은 수천 건, 1분 이상).
    같은 날 반복 조회(현재·과거 시점 비교 등)를 위해 6시간 캐시한다."""
    from _us_common import read_cache, write_cache
    name = f"dart_{endpoint}_{corp_code}"
    rows = read_cache(name, _HOLDINGS_CACHE_TTL)
    if rows is None:
        rows = _api_json(f"{endpoint}.json", {"corp_code": corp_code}, timeout=_TIMEOUT_BULK).get("list") or []
        write_cache(name, rows)
    return rows


_INSIDER_CAVEAT = ("증감 사유(장내매수·매도·주식보상·상속·증여 등)는 이 API에 없다. 큰 변동은 원문(접수번호 링크)으로 "
                   "사유를 확인하고, 증가를 곧 매수 신호로 읽지 않는다.")


def _window(rows: list, as_of: str, days: int) -> list:
    """접수일이 (as_of - days, as_of] 안인 보고, 접수일·접수번호 순."""
    end = datetime.strptime(as_of, "%Y-%m-%d").date()
    start = (end - timedelta(days=days)).strftime("%Y-%m-%d")
    picked = [r for r in rows if start < (r.get("rcept_dt") or "") <= as_of]
    return sorted(picked, key=lambda r: (r.get("rcept_dt", ""), r.get("rcept_no", "")))


def _shares(value) -> int:
    v = _parse_amount(value)
    return int(v) if v is not None else 0


def summarize_insiders(rows: list, as_of: str, days: int) -> dict:
    """elestock 행 → 기간 요약. 순수 함수(테스트용)."""
    win = _window(rows, as_of, days)
    people = {}
    for r in win:
        d = _shares(r.get("sp_stock_lmp_irds_cnt"))
        p = people.setdefault(r.get("repror", ""), {"이름": r.get("repror", ""), "보고": 0, "순증감": 0,
                                                    "증가": 0, "감소": 0})
        p["보고"] += 1
        p["순증감"] += d
        if d:
            p["증가" if d > 0 else "감소"] += d
        p.update({"등기": r.get("isu_exctv_rgist_at", ""), "직위": r.get("isu_exctv_ofcps", ""),
                  "주요주주": r.get("isu_main_shrholdr", ""), "보유": _shares(r.get("sp_stock_lmp_cnt")),
                  "최근접수": r.get("rcept_dt", "")})
    deltas = [_shares(r.get("sp_stock_lmp_irds_cnt")) for r in win]
    return {
        "rows": win, "people": sorted(people.values(), key=lambda p: -abs(p["순증감"])),
        "증가건": sum(1 for d in deltas if d > 0), "증가주식": sum(d for d in deltas if d > 0),
        "감소건": sum(1 for d in deltas if d < 0), "감소주식": sum(d for d in deltas if d < 0),
    }


def summarize_major(rows: list, as_of: str, days: int) -> dict:
    """majorstock 행 → as_of 시점 보고자별 최신 지분 + 기간 내 변동 보고. 순수 함수(테스트용)."""
    known = sorted((r for r in rows if (r.get("rcept_dt") or "") <= as_of),
                   key=lambda r: (r.get("rcept_dt", ""), r.get("rcept_no", "")))
    latest = {}
    for r in known:
        latest[r.get("repror", "")] = r
    holders = sorted(latest.values(), key=lambda r: -(_parse_amount(r.get("stkrt")) or 0))
    return {"holders": holders, "changes": _window(rows, as_of, days)}


def _fmt_delta(n: int) -> str:
    return f"{n:+,}주" if n else "0주"


def _link(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def cmd_insiders(code: str, days=180, as_of=None, top=10):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")
    as_of = as_of or date.today().strftime("%Y-%m-%d")
    rows = _holdings_rows("elestock", corp_code)
    s = summarize_insiders(rows, as_of, days)
    if not s["rows"]:
        _die(f"NO_DATA: {corp_name}({code}) 의 임원·주요주주 소유 보고가 {as_of} 이전 {days}일 동안 없습니다.", 3)
    net = s["증가주식"] + s["감소주식"]
    print("=" * 64)
    print(f"임원·주요주주 소유 보고: {corp_name} ({code.zfill(6)}) — {as_of} 이전 {days}일 접수분")
    print("=" * 64)
    print(f"  보고 {len(s['rows'])}건 · 보고자 {len(s['people'])}명")
    print(f"  증가 {s['증가건']}건({_fmt_delta(s['증가주식'])}) · 감소 {s['감소건']}건({_fmt_delta(s['감소주식'])}) · "
          f"순증감 {_fmt_delta(net)}")
    print(f"  ⚠️ {_INSIDER_CAVEAT}")
    key = [p for p in s["people"] if p["등기"] == "등기임원" or p["주요주주"] not in ("", "-")]
    if key:
        print("\n  [등기임원·주요주주]")
        for p in key[:top]:
            role = "/".join(x for x in (p["등기"], p["직위"], p["주요주주"] if p["주요주주"] != "-" else "") if x)
            print(f"    {p['이름']} ({role}) 순증감 {_fmt_delta(p['순증감'])} · 보유 {p['보유']:,}주 · "
                  f"보고 {p['보고']}건 · 최근 {p['최근접수']}")
    print(f"\n  [보고자별 순증감 상위 {min(top, len(s['people']))}]")
    for p in s["people"][:top]:
        print(f"    {p['이름']} ({p['등기']}/{p['직위']}) 순증감 {_fmt_delta(p['순증감'])} · "
              f"보유 {p['보유']:,}주 · 보고 {p['보고']}건")
    print(f"\n  [최근 보고 {min(top, len(s['rows']))}건]")
    for r in s["rows"][-top:][::-1]:
        print(f"    [{r.get('rcept_dt')}] {r.get('repror')} ({r.get('isu_exctv_ofcps')}) "
              f"{_fmt_delta(_shares(r.get('sp_stock_lmp_irds_cnt')))} → 보유 {_shares(r.get('sp_stock_lmp_cnt')):,}주")
        print(f"        {_link(r.get('rcept_no', ''))}")
    print("\n  출처: DART 임원ㆍ주요주주 특정증권등 소유상황보고서(OpenDART elestock). 증감은 직전 보고 대비.")


def cmd_major_holders(code: str, days=365, as_of=None):
    corp_code, corp_name = _resolve(code)
    if not corp_code:
        _die(f"❌ 종목코드 {code} 에 해당하는 상장사를 DART에서 찾을 수 없습니다.")
    as_of = as_of or date.today().strftime("%Y-%m-%d")
    rows = _holdings_rows("majorstock", corp_code)
    s = summarize_major(rows, as_of, days)
    if not s["holders"]:
        _die(f"NO_DATA: {corp_name}({code}) 의 대량보유(5%) 보고가 {as_of} 까지 없습니다.", 3)
    print("=" * 64)
    print(f"대량보유(5% 이상) 보고: {corp_name} ({code.zfill(6)}) — {as_of} 까지 접수분")
    print("=" * 64)
    print("  [보고자별 최신 보고 — 특별관계자 합산 지분율]")
    for r in s["holders"]:
        below = (_parse_amount(r.get("stkrt")) or 0) < 5
        print(f"    {r.get('repror')}: {r.get('stkrt')}% ({_shares(r.get('stkqy')):,}주) · "
              f"최근 {r.get('rcept_dt')} {r.get('report_tp', '')}"
              + (" — 5% 미만으로 내려간 보고, 이후 변동은 보고 의무 없음(현재 지분 불명)" if below else ""))
    print(f"\n  [{as_of} 이전 {days}일 변동 보고 {len(s['changes'])}건]")
    for r in s["changes"][::-1][:15]:
        reason = " / ".join(x.strip("- ").strip() for x in (r.get("report_resn") or "").splitlines() if x.strip())
        print(f"    [{r.get('rcept_dt')}] {r.get('repror')} {_fmt_delta(_shares(r.get('stkqy_irds')))} "
              f"→ {r.get('stkrt')}% ({r.get('stkrt_irds')}%p) · {reason}")
        print(f"        {_link(r.get('rcept_no', ''))}")
    if not s["changes"]:
        print("    (없음)")
    print("\n  출처: DART 주식등의 대량보유상황보고서(OpenDART majorstock). 5% 이상 보유자·1%p 이상 변동 시 보고.")


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

    pi = sub.add_parser("insiders", help="임원·주요주주 소유 보고(내부자 지분 변동)")
    pi.add_argument("code")
    pi.add_argument("--days", type=int, default=180, help="기준일 이전 조회 기간(일, 기본 180)")
    pi.add_argument("--top", type=int, default=10, help="표시 인원·건수(기본 10)")
    pi.add_argument("--as-of", default="", help="이 날짜까지 접수된 보고(YYYY-MM-DD)")

    pm = sub.add_parser("major-holders", help="5% 이상 대량보유 보고")
    pm.add_argument("code")
    pm.add_argument("--days", type=int, default=365, help="변동 보고 조회 기간(일, 기본 365)")
    pm.add_argument("--as-of", default="", help="이 날짜까지 접수된 보고(YYYY-MM-DD)")

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
        elif args.cmd == "insiders":
            cmd_insiders(args.code, args.days, _as_of(args.as_of), args.top)
        elif args.cmd == "major-holders":
            cmd_major_holders(args.code, args.days, _as_of(args.as_of))
    except (ConnectionError, RuntimeError) as e:
        _die(f"❌ {e}")


if __name__ == "__main__":
    main()
