---
name: financial-data
description: "재무 데이터 수집·교차 검증 규범: 모든 핵심 데이터는 2개 독립 출처에서 가져오고 오차 >1%를 표기. 재무 데이터를 다루는 모든 리서치에 적용."
---

# 재무 데이터 수집 및 교차 검증 규범

본 규범은 기업 재무 데이터를 다루는 모든 리서치에 적용된다. **모든 핵심 데이터는 두 개의 독립된 출처에서 가져와야 하며, 오차가 1%를 초과하면 반드시 표기한다.**

---

## 데이터 소스 우선순위

### 미국 주식 (PDD, 텐센트 ADR, 넷이즈 ADR 등)

| 우선순위 | 출처 | URL | 접근 방법 |
|--------|------|-----|---------|
| 1 (주) | **macrotrends** | macrotrends.net/stocks/charts/{ticker} | 직접 접속, 가입 불필요 |
| 2 (부) | **stockanalysis** | stockanalysis.com/stocks/{ticker}/financials | 직접 접속, 가입 불필요 |
| 원본 1차 자료 | SEC EDGAR | sec.gov/cgi-bin/browse-edgar | `python3 tools/sec_edgar_data.py financials {티커}` (XBRL 공시 원본, 키 불필요) / 10-K·10-Q 원문 |

> **미국 주식 보조 도구** (stdlib만, `tools/`):
> - `sec_edgar_data.py financials|filings {티커}` — 공시 원본 재무·공시 목록. `SEC_EDGAR_USER_AGENT="이름 이메일"` 설정 권장(SEC가 연락처 없는 요청 거부).
> - `alphavantage_data.py overview|statement|news|insider|daily|indicator` — 부 출처·뉴스 감성·내부자 거래. `ALPHA_VANTAGE_API_KEY` 필요(무료 하루 25회).
> - `fred_data.py series {별칭|시리즈ID}` — 금리·물가·고용 등 거시 지표. `FRED_API_KEY` 필요(무료).
> - `polymarket_data.py search "{주제}"` — 금리 인하·경기침체 등 사건의 예측시장 확률(실시간만).
>
> **과거 시점 분석(`--as-of YYYY-MM-DD`)**: SEC는 그날까지 공시된 값(이후 정정 전), FRED는 그 시점 발표 빈티지를 준다. 공시일을 알 수 없는 데이터(AV 재무·개요·내부자, Polymarket)는 보류한다.
>
> **종료 코드와 첫 줄**: `NO_DATA`(3) 데이터 없음 / `UNAVAILABLE`(4) 출처 장애 / `WITHHELD`(5) 시점 보류 / `NOT_CONFIGURED`(6) 키 없음. 어느 경우든 값을 추정해 채우지 말고 "데이터 없음/조회 불가"로 기록한 뒤 다른 출처로 교차 확인한다. `UNAVAILABLE`은 종목에 데이터가 없다는 뜻이 아니다.

### 홍콩 주식 (텐센트 0700, 넷이즈 9999, 메이투안 3690 등)

| 우선순위 | 출처 | URL | 접근 방법 |
|--------|------|-----|---------|
| 1 (주) | **aastocks** | aastocks.com/tc/stocks/analysis/company-fundamental | 직접 접속 |
| 2 (부) | **macrotrends** (ADR 코드) | 텐센트는 TCEHY, 넷이즈는 NTES | 직접 접속 |
| 원본 1차 자료 | HKEX 공시 시스템 | hkexnews.hk | 연차보고서 PDF |

### 중국 A주 (37 Interactive, G-bits 등)

| 우선순위 | 출처 | URL | 접근 방법 |
|--------|------|-----|---------|
| 1 (주) | **East Money** | eastmoney.com → 종목코드 검색 → 재무제표 | 직접 접속 |
| 2 (부) | **cninfo** | cninfo.com.cn | 원본 연차/분기 보고서 PDF |

### 한국 주식 (삼성전자, SK하이닉스 등)

| 우선순위 | 출처 | URL | 접근 방법 |
|--------|------|-----|---------|
| 1 (주) | **DART 전자공시** | dart.fss.or.kr | `python3 tools/dart_data.py financials {종목코드}` (OpenAPI, 1차 공시 원본) / 웹은 사업보고서 원문 |
| 2 (부) | **네이버 금융** | finance.naver.com | `python3 tools/global_stock_data.py financials {종목코드}` (네이버·Yahoo 교차) |

> **한국 주식 수집 절차**: 먼저 `tools/dart_data.py financials {종목코드}` 로 DART 원본(연결 재무, 3개년)을 확보한다.
> `DART_API_KEY` 환경변수가 필요하다(opendart.fss.or.kr 무료 발급, 일 20,000건). 키가 없으면 도구가 안내 메시지를 출력한다.
> 이어서 `tools/global_stock_data.py financials {종목코드}` 의 네이버 값을 부 출처로 두고 오차 >1% 를 표기한다.
> **과거 시점 분석**: `tools/dart_data.py financials {종목코드} --as-of YYYY-MM-DD` 는 그날까지 **접수된** 정기보고서만 쓴다(사업연도가 끝났어도 공시 전이면 쓰지 않음). DART가 그 뒤에 접수된 정정공시 값을 돌려주면 수치를 보류(`WITHHELD`, 종료 코드 5)하고 그 시점 공시 문서 링크를 준다 — 이때 값을 추정하지 말고 원문을 확인한다. `disclosures --as-of` 는 정정 전 원공시까지 포함한 그 시점 공시 목록을 보여준다.

---

## 실행 규범

### 1단계: 데이터 수집

각 재무 지표(매출, 순이익, 매출총이익률, 영업현금흐름, 부채비율 등)에 대해 **출처 1**과 **출처 2**에서 각각 수치를 가져온다.

### 2단계: 오차 계산 및 표기

```
오차율 = |출처1 수치 - 출처2 수치| / 출처1 수치 × 100%
```

| 오차 | 처리 방법 |
|------|---------|
| ≤ 1% | ✅ 일치. 출처 1의 수치를 사용하고 두 출처를 모두 표기 |
| 1% ~ 5% | ⚠️ "데이터 차이 존재"로 표기. 두 수치를 병기하고 가능한 원인(환율/회계 기준) 설명 |
| > 5% | ❌ "데이터 중대 차이"로 표기. 반드시 원본 재무제표로 검증해야 하며 그대로 사용 금지 |

### 3단계: 데이터 표기 형식

모든 핵심 데이터는 아래 형식으로 표기한다:

```
매출: 1,239억 위안 ✅
  - macrotrends: 1,241억 위안
  - stockanalysis: 1,237억 위안
  - 오차: 0.3%
```

차이가 있는 경우의 예시:
```
순이익: 245억 위안 ⚠️ 데이터 차이 존재
  - macrotrends: 245억 위안 (GAAP)
  - stockanalysis: 278억 위안 (Non-GAAP)
  - 오차: 13.5% — 원인: 회계 기준 차이 (GAAP vs Non-GAAP)
```

---

## 흔한 차이 원인 (데이터 오류가 아닐 수 있음)

| 원인 | 설명 |
|------|------|
| GAAP vs Non-GAAP | 가장 흔한 원인. 특히 이익 관련 데이터 |
| 환율 환산 | 홍콩달러/위안/달러/원화 환산 시점 차이 |
| 회계연도 정의 | 역년 vs 회계연도 (예: 애플은 회계연도가 10월 종료) |
| 연결 기준 | 비지배지분(소수주주지분) 포함 여부 |
| 데이터 갱신 지연 | 일부 플랫폼이 최신 분기 실적을 아직 반영하지 않음 |

---

## 특별 규칙

1. **비상장 회사** (miHoYo, Lilith 등): 1차 데이터 출처가 하나뿐인 경우 데이터 앞에 `[추정]`을 표기하고 교차 검증은 생략한다
2. **분기 데이터 vs 연간 데이터**: 교차 검증은 연간 데이터를 우선 사용한다. 분기 데이터는 일부 출처에서 갱신이 지연될 수 있다
3. **원본 재무제표 우선**: 두 출처 모두 원본 재무제표(10-K/연차보고서 PDF)와 다르면 원본 재무제표를 기준으로 하고, 출처 오류를 표기한다

---

## 빠른 참조

| 대상 | 주 출처 | 보조 출처 |
|------|---------|---------|
| PDD / 핀둬둬 | macrotrends.net/stocks/charts/PDD | stockanalysis.com/stocks/pdd |
| 텐센트 | macrotrends.net/stocks/charts/TCEHY | aastocks (0700.HK) |
| 넷이즈 | macrotrends.net/stocks/charts/NTES | aastocks (9999.HK) |
| 37 Interactive | eastmoney.com (002555) | cninfo.com.cn |
| G-bits | eastmoney.com (603444) | cninfo.com.cn |
| Nintendo | macrotrends.net/stocks/charts/NTDOY | stockanalysis.com/stocks/ntdoy |
| Capcom | macrotrends (CCOEY) | stockanalysis (CCOEY) |
| 삼성전자 | dart.fss.or.kr (005930) | finance.naver.com |
