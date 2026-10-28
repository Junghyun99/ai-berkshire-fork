#!/usr/bin/env python3
"""FRED 거시경제 데이터 도구 — 세인트루이스 연준 공식 API, 외부 종속성 없음(stdlib만).

금리·국채수익률·물가·고용·성장 등 거시 시계열을 가져온다. 산업·기업 리서치에서
거시 환경을 헤드라인이 아니라 실제 수치로 뒷받침할 때 쓴다.

시점 통제(--as-of):
  CPI·GDP처럼 나중에 수정(revision)되는 지표는, 오늘 조회하면 '수정된 최신값'이 나온다.
  --as-of 를 주면 FRED의 realtime(빈티지) 파라미터를 그 날짜로 고정해, 그 시점에 실제로
  발표돼 있던 값만 보여준다(ALFRED 빈티지). 과거 시점 분석에 미래 수정치가 섞이지 않게 한다.

설계 출처: TradingAgents(github.com/TauricResearch/TradingAgents, Apache 2.0)
  tradingagents/dataflows/vendors/fred.py 를 stdlib로 이식.

사전 준비:
  무료 API 키 발급: https://fred.stlouisfed.org/docs/api/api_key.html
      export FRED_API_KEY=발급받은키

사용법:
    python3 tools/fred_data.py series cpi                         # 별칭 사용, 최근 1년
    python3 tools/fred_data.py series 10y_treasury --lookback 730 # 최근 2년
    python3 tools/fred_data.py series CPIAUCSL --as-of 2022-06-30 # 2022-06-30 시점에 발표돼 있던 값
    python3 tools/fred_data.py aliases                            # 별칭 목록

종료 코드: 0 정상 / 3 데이터 없음 / 4 출처 장애 / 6 키 없음 (tools/_us_common.py 참고)
필요 Python >= 3.8, 외부 종속성 없음.
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

from _us_common import (
    NoDataError, NotConfiguredError, UnavailableError, http_get, parse_as_of, run,
)

_BASE = "https://api.stlouisfed.org/fred"
_DEFAULT_LOOKBACK = 365
# 일별 시계열(금리·VIX)을 긴 기간 조회하면 출력이 넘치므로 최근 N개만 표로 보여준다.
_MAX_ROWS = 40

# 별칭 → FRED 시리즈 ID. 목록에 없는 값은 FRED 시리즈 ID로 그대로 사용한다.
MACRO_SERIES = {
    # 정책금리·국채
    "fed_funds_rate": "FEDFUNDS", "fed_funds": "FEDFUNDS",
    "2y_treasury": "DGS2", "10y_treasury": "DGS10", "30y_treasury": "DGS30",
    "10y_2y_spread": "T10Y2Y", "yield_curve": "T10Y2Y",
    # 물가
    "cpi": "CPIAUCSL", "core_cpi": "CPILFESL", "pce": "PCEPI", "core_pce": "PCEPILFE",
    "inflation_expectations": "T10YIE",
    # 성장
    "real_gdp": "GDPC1", "gdp": "GDP", "industrial_production": "INDPRO",
    # 고용
    "unemployment": "UNRATE", "unemployment_rate": "UNRATE",
    "nonfarm_payrolls": "PAYEMS", "payrolls": "PAYEMS", "initial_claims": "ICSA",
    # 통화·시장
    "m2": "M2SL", "money_supply": "M2SL", "vix": "VIXCLS", "dollar_index": "DTWEXBGS",
    # 심리·주택·소비
    "consumer_sentiment": "UMCSENT", "housing_starts": "HOUST", "retail_sales": "RSAFS",
    # 유로존
    "ecb_deposit_rate": "ECBDFR", "euro_hicp": "CP0000EZ19M086NEST",
    "germany_10y": "IRLTLT01DEM156N", "eur_usd": "DEXUSEU",
    # 한국·환율(FRED 미러)
    "korea_10y": "IRLTLT01KRM156N", "usd_krw": "DEXKOUS",
}


def _api_key() -> str:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise NotConfiguredError(
            "FRED_API_KEY 환경변수가 없습니다. https://fred.stlouisfed.org/docs/api/api_key.html "
            "에서 무료 발급 후 export FRED_API_KEY=키 로 설정하세요(키는 저장소에 저장하지 말 것).")
    return key


def resolve_series_id(indicator: str) -> str:
    """별칭이면 시리즈 ID로, 아니면 그대로. 공백이 있거나 너무 긴 값은 시리즈 ID가 아니므로 거부한다."""
    key = indicator.strip().lower().replace(" ", "_").replace("-", "_")
    if key in MACRO_SERIES:
        return MACRO_SERIES[key]
    candidate = indicator.strip().upper()
    if not candidate or len(candidate) > 30 or any(c.isspace() for c in candidate):
        raise NoDataError(f"'{indicator}' 는 알려진 별칭도, 유효한 FRED 시리즈 ID도 아닙니다. "
                          f"aliases 명령으로 별칭을 확인하세요.")
    return candidate


def _fred_today() -> str:
    """FRED 기준 오늘(미국 중부시간). realtime 날짜가 FRED의 '오늘'보다 미래면 400을 돌려준다.

    중부시간은 UTC-6(표준)/-5(서머타임). 보수적으로 UTC-6을 쓰면 하루 앞서는 일이 없다.
    """
    return (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")


def _request(path: str, params: dict) -> dict:
    key = _api_key()
    status, body = http_get(f"{_BASE}/{path}",
                            dict(params, api_key=key, file_type="json"), secret=key)
    try:
        data = json.loads(body)
    except ValueError:
        raise UnavailableError(f"FRED HTTP {status}: JSON이 아닌 응답")
    if status == 400:
        # 없는 시리즈 ID·잘못된 파라미터: {"error_message": ...}
        message = str(data.get("error_message", "")).replace(key, "***")
        raise NoDataError(f"FRED 요청 거부: {message}")
    if not 200 <= status < 300:
        raise UnavailableError(f"FRED HTTP {status}")
    return data


def cmd_series(indicator: str, as_of: str, lookback: int):
    series_id = resolve_series_id(indicator)
    end_dt = datetime.strptime(as_of, "%Y-%m-%d")
    start = (end_dt - timedelta(days=lookback)).strftime("%Y-%m-%d")
    # 빈티지 고정: realtime 구간을 하루로 고정하면 '그 시점에 알려진 값'을 받는다. FRED의 오늘로 자른다.
    pit = min(as_of, _fred_today())
    realtime = {"realtime_start": pit, "realtime_end": pit}

    meta = _request("series", dict(series_id=series_id, **realtime)).get("seriess") or []
    if not meta:
        raise NoDataError(f"FRED 시리즈 '{series_id}' 를 찾을 수 없습니다.")
    info = meta[0]
    obs = _request("series/observations", dict(
        series_id=series_id, observation_start=start, observation_end=as_of,
        sort_order="asc", **realtime)).get("observations", [])
    # FRED는 결측을 "."로 표기한다.
    points = [(o["date"], o["value"]) for o in obs if o.get("value") not in (".", None, "")]

    seasonal = info.get("seasonal_adjustment_short", "")
    print("=" * 64)
    print(f"FRED: {info.get('title', series_id)} ({series_id})")
    print(f"  단위: {info.get('units_short') or info.get('units', '')} | "
          f"주기: {info.get('frequency', '')}{f' ({seasonal})' if seasonal else ''}")
    print(f"  기간: {start} ~ {as_of} | 빈티지: {pit} 시점에 발표된 값")
    print("=" * 64)

    if not points:
        raise NoDataError(
            f"{series_id} 의 {start}~{as_of} 관측치가 {pit} 빈티지에 없습니다. "
            f"발표 주기보다 기간이 짧거나(--lookback 늘리기), 그 시점에 아직 발표 전일 수 있습니다.")

    first_d, first_v = points[0]
    last_d, last_v = points[-1]
    try:
        delta = float(last_v) - float(first_v)
        pct = f" ({delta / float(first_v) * 100:+.2f}%)" if float(first_v) else ""
        print(f"  최신: {last_v} ({last_d}) | {first_d}→{last_d} 변화: {delta:+.2f}{pct}, 시작값 {first_v}")
    except ValueError:
        print(f"  최신: {last_v} ({last_d})")

    shown = points[-_MAX_ROWS:]
    if len(points) > _MAX_ROWS:
        print(f"  (관측치 {len(points)}개 중 최근 {_MAX_ROWS}개만 표시)")
    print("\n  날짜        | 값")
    for d, v in shown:
        print(f"  {d}  | {v}")
    print("\n  출처: FRED(api.stlouisfed.org), 세인트루이스 연방준비은행.")


def cmd_aliases():
    print("FRED 별칭 → 시리즈 ID (목록에 없는 값은 FRED 시리즈 ID로 그대로 사용)")
    for alias, sid in MACRO_SERIES.items():
        print(f"  {alias:<24} {sid}")


def main():
    p = argparse.ArgumentParser(description="FRED 거시경제 시계열 도구.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("series", help="시계열 조회")
    ps.add_argument("indicator", help="별칭(cpi, 10y_treasury 등) 또는 FRED 시리즈 ID")
    ps.add_argument("--as-of", default="", help="이 날짜 시점의 빈티지(YYYY-MM-DD, 기본 오늘)")
    ps.add_argument("--lookback", type=int, default=_DEFAULT_LOOKBACK, help="조회 기간(일), 기본 365")
    sub.add_parser("aliases", help="별칭 목록")

    args = p.parse_args()
    if args.cmd == "series":
        cmd_series(args.indicator, parse_as_of(args.as_of), args.lookback)
    else:
        cmd_aliases()


if __name__ == "__main__":
    run(main)
