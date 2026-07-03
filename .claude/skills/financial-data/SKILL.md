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
| 원본 1차 자료 | SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 10-K / 10-Q 원문 |

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
| 1 (주) | **DART 전자공시** | dart.fss.or.kr | 사업보고서/분기보고서 원문 |
| 2 (부) | **네이버 금융** | finance.naver.com | 종목코드 검색 → 재무분석 |

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
