---
name: ta-fundamentals-analyst
role: Fundamentals Analyst (기본적 분석가)
description: "TradingAgents 분석가 팀. 회사 개요·재무제표 3종·내부자 거래로 기본적 정보를 최대한 자세히 정리한다."
model_tier: quick
tools: get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_transactions
output: state.fundamentals_report (자유 서술 + 마크다운 표)
source: tradingagents/agents/analysts/fundamentals_analyst.py
---

# Fundamentals Analyst — 기본적 분석가

## 역할 요약
- 회사 프로필, 기본 재무, 재무 이력을 모아 **트레이더가 회사의 기본 정보를 한눈에 보게** 한다.
- "최대한 자세히" 쓰라고 지시받는다. 가치 판단보다는 정보 집약이 목적이다.

## 도구
| 도구 | 인자 | 용도 |
|---|---|---|
| `get_fundamentals` | ticker, curr_date | 종합 기본 정보 |
| `get_balance_sheet` | ticker, freq, curr_date | 재무상태표 |
| `get_cashflow` | ticker, freq, curr_date | 현금흐름표 |
| `get_income_statement` | ticker, freq, curr_date | 손익계산서 |
| `get_insider_transactions` | ticker | 최근 내부자 매매 |

데이터 출처는 yfinance / Alpha Vantage / SEC EDGAR(공시 원본, "as filed") 중 설정에 따라 라우팅된다. 과거 날짜 실행에서는 그 날짜까지 **공시된** 재무만 보이도록 처리한다(v0.5.0~v0.7.1 변경 이력).

## 역할 프롬프트 원문
껍데기는 [shared-prompts.md](../shared-prompts.md) §1.

```text
You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read. Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements, and `get_insider_transactions` for recent insider buying and selling.{language_instruction}
```

## 핵심 지시 (한국어 요약)
1. 재무 문서, 회사 프로필, 기본 재무, 재무 이력을 포괄.
2. 최대한 상세하게, 근거 있는 실행 가능한 인사이트.
3. 끝에 마크다운 요약 표.
4. 도구 5개의 쓰임새를 명시.

## 출력
- 자유 서술 + 표 → `state.fundamentals_report`
- 하위 프롬프트에서는 "Company fundamentals report" 라벨. 코인이면 "Asset fundamentals report (may be unavailable for crypto)".

## ai-berkshire 관점에서 본 한계
- 프롬프트에 **해자·현금흐름 질·자본배분 같은 평가 틀이 없다.** 정보 나열형이다. 이 저장소의 `master-buffett`(현금흐름 최우선, 이익의 질 점검)과 비교하면 분석 깊이보다 속도·범용성을 택한 설계다.
- "over the past week"라는 표현은 재무제표 분석에는 어울리지 않는다. 뉴스 애널리스트 프롬프트에서 복사해 온 흔적으로 보인다(추측).
