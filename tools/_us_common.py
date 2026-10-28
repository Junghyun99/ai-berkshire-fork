"""미국 데이터 도구 공통 모듈 — sec_edgar_data / fred_data / polymarket_data / alphavantage_data 가 공유.

외부 종속성 없음(stdlib + curl). 다른 tools/ 스크립트처럼 curl로 요청해 시스템 프록시를 따른다.

TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)의 데이터 계층 설계를 이식:
  - 실패를 성격별로 구분해 종료 코드로 알린다. 스킬(Claude)이 "데이터 없음"을 추정값으로 채우지 않게 하기 위함.
  - 시점 통제(as-of): 과거 날짜를 주면 그 날짜에 공개돼 있던 데이터만 쓰고, 날짜를 알 수 없는 데이터는 보류한다.

종료 코드:
  0 정상 / 3 데이터 없음(NO_DATA) / 4 출처 장애(UNAVAILABLE) / 5 시점 보류(WITHHELD) / 6 미설정(API 키 없음)
  (1은 일반 오류, 2는 argparse 사용법 오류로 남겨 둔다)
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime
from urllib.parse import urlencode

_TIMEOUT = 30
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

EXIT_NOT_CONFIGURED = 6
EXIT_NO_DATA = 3
EXIT_UNAVAILABLE = 4
EXIT_WITHHELD = 5


class NotConfiguredError(Exception):
    """API 키 등 설정이 없어 출처를 쓸 수 없음."""


class NoDataError(Exception):
    """출처는 응답했지만 쓸 수 있는 데이터가 없음(종목 없음·기간 내 데이터 없음 등)."""


class UnavailableError(Exception):
    """출처가 응답하지 못함(네트워크·요청 한도·서버 오류). 종목에 대해서는 아무것도 말해주지 않는다."""


def http_get(url: str, params: dict = None, headers: dict = None, secret: str = "",
             timeout: int = _TIMEOUT) -> tuple:
    """GET 요청 → (HTTP 상태코드, 본문 문자열). 네트워크 실패는 UnavailableError.

    secret(API 키)은 오류 메시지에서 가린다. 출처가 키를 응답에 되돌려 보내는 경우가 있다.
    """
    full = f"{url}?{urlencode(params)}" if params else url
    cmd = ["curl", "-sS", "-L", "--retry", "2", "-w", "\n%{http_code}"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(full)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UnavailableError(f"요청 시간 초과({timeout}s): {url}")
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", "replace").strip()
        if secret:
            err = err.replace(secret, "***")
        raise UnavailableError(f"요청 실패({url}): {err or 'curl 오류'}")
    body, _, code = result.stdout.decode("utf-8", "replace").rpartition("\n")
    try:
        status = int(code)
    except ValueError:
        status = 0
    return status, body


def get_json(url: str, params: dict = None, headers: dict = None, secret: str = "") -> dict:
    """GET → JSON. 2xx가 아니거나 JSON이 아니면 UnavailableError."""
    status, body = http_get(url, params, headers, secret)
    if not 200 <= status < 300:
        raise UnavailableError(f"HTTP {status}: {url}")
    try:
        return json.loads(body)
    except ValueError:
        raise UnavailableError(f"JSON이 아닌 응답: {url}")


def read_cache(name: str, max_age_seconds: int):
    """tools/.cache/{name} 이 max_age 이내면 JSON 반환, 아니면 None. 손상된 파일은 캐시 미스로 취급."""
    path = os.path.join(CACHE_DIR, name)
    try:
        if datetime.now().timestamp() - os.path.getmtime(path) < max_age_seconds:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except (OSError, ValueError):
        pass
    return None


def write_cache(name: str, data) -> None:
    """임시 파일에 쓴 뒤 교체해, 읽는 쪽이 반쯤 쓰인 파일을 보지 않게 한다."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 시점 통제(as-of)
# ---------------------------------------------------------------------------

def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def parse_as_of(value: str) -> str:
    """--as-of 값을 YYYY-MM-DD로 정규화. 미래 날짜는 오늘로 자른다(미래 데이터 요청 방지).

    "2026-7-3"을 문자열 그대로 비교하면 "2026-07-23"보다 늦은 날짜로 판정되므로 반드시 정규화한다.
    """
    if not value:
        return today()
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"❌ --as-of 형식 오류: {value} (YYYY-MM-DD)")
    return min(d, date.today()).strftime("%Y-%m-%d")


def is_historical(as_of: str) -> bool:
    """as-of가 오늘보다 과거인가. 과거면 '현재 시점만 제공되는' 데이터는 보류해야 한다."""
    return bool(as_of) and as_of < today()


def withheld(source: str, what: str, as_of: str, reason: str, alternative: str = "") -> None:
    """시점 보류 안내를 출력하고 종료(코드 5). 데이터를 내놓지 않는 것이 정상 동작임을 명시한다."""
    print(f"WITHHELD: {source} {what} — {as_of} 기준 분석에서는 제공하지 않습니다.")
    print(f"  이유: {reason}")
    if alternative:
        print(f"  대안: {alternative}")
    print("  이 데이터를 추정하거나 현재 값으로 대신 채우지 마세요.")
    sys.exit(EXIT_WITHHELD)


# ---------------------------------------------------------------------------
# 실패 처리 — 진입점에서 한 번에
# ---------------------------------------------------------------------------

def run(main_func) -> None:
    """main을 실행하고 예외를 종료 코드 + 기계가 읽을 수 있는 첫 줄로 바꾼다.

    첫 줄 접두어(NO_DATA / UNAVAILABLE / NOT_CONFIGURED)는 스킬이 grep할 수 있게 영어로 고정한다.
    """
    try:
        main_func()
    except NotConfiguredError as e:
        print(f"NOT_CONFIGURED: {e}")
        sys.exit(EXIT_NOT_CONFIGURED)
    except NoDataError as e:
        print(f"NO_DATA: {e}")
        print("  쓸 수 있는 데이터가 없습니다. 값을 추정하거나 지어내지 말고 '데이터 없음'으로 기록하세요.")
        sys.exit(EXIT_NO_DATA)
    except UnavailableError as e:
        print(f"UNAVAILABLE: {e}")
        print("  출처가 지금 응답하지 못했습니다. 종목에 데이터가 없다는 뜻이 아닙니다. "
              "다른 출처로 교차 확인하고, 값을 지어내지 마세요.")
        sys.exit(EXIT_UNAVAILABLE)


def fmt_usd_millions(value) -> str:
    """달러 → 백만 달러, 천 단위 구분. 1백만 미만은 유효숫자 3자리(0으로 찍히지 않게)."""
    if value is None:
        return "-"
    m = value / 1e6
    if m == 0 or abs(m) >= 1:
        return f"{m:,.0f}"
    return f"{m:.3g}"
