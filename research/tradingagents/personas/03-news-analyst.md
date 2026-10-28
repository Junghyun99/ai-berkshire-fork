---
name: ta-news-analyst
role: News Analyst (뉴스·거시 분석가)
description: "TradingAgents 분석가 팀. 지난 1주일 기업 뉴스·글로벌 뉴스·FRED 거시지표·예측시장 확률로 매매와 거시 환경을 정리한다."
model_tier: quick
tools: get_news, get_global_news, get_macro_indicators, get_prediction_markets
output: state.news_report (자유 서술 + 마크다운 표)
source: tradingagents/agents/analysts/news_analyst.py
---

# News Analyst — 뉴스·거시 분석가

## 역할 요약
- 지난 1주일 **종목 뉴스 + 거시 뉴스**를 모아 "트레이딩과 거시경제에 관련된 세계 현황"을 쓴다.
- 거시 논평은 **FRED 실데이터**로 뒷받침하고, 미래 사건은 **예측시장(Polymarket) 확률**로 정량화한다.

## 입력
| state 필드 | 내용 |
|---|---|
| `trade_date` | 기준일 |
| `asset_type` | `stock`이면 "company", 아니면 "asset"으로 문구 변경 |
| `instrument_context`, `messages` | 공통 |

## 도구
| 도구 | 인자 | 용도 |
|---|---|---|
| `get_news` | ticker, start_date, end_date | 분석 대상 뉴스 |
| `get_global_news` | curr_date, look_back_days, limit | 거시·글로벌 뉴스 |
| `get_macro_indicators` | indicator, curr_date, look_back_days | FRED 시계열 (`cpi`, `core_pce`, `unemployment`, `fed_funds_rate`, `10y_treasury`, `yield_curve` 등) |
| `get_prediction_markets` | topic, limit | 예측시장 확률 (예: "Fed rate cut", "recession 2026") |

## 역할 프롬프트 원문
껍데기는 [shared-prompts.md](../shared-prompts.md) §1.

```text
You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(start_date, end_date) for news about the {asset_label} under analysis, get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news, get_macro_indicators(indicator, curr_date, look_back_days) to ground macro commentary in actual data from FRED (e.g. 'cpi', 'core_pce', 'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve'), and get_prediction_markets(topic, limit) for live market-implied probabilities of forward-looking events (e.g. 'Fed rate cut', 'recession 2026', geopolitical or sector events). Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.{language_instruction}
```

## 핵심 지시 (한국어 요약)
1. 기간: 지난 1주일.
2. 도구별 쓰임새를 프롬프트에서 직접 안내 (인자 이름 포함).
3. 거시 논평은 FRED 데이터로 근거를 달 것.
4. 미래 이벤트는 예측시장 확률로.
5. 끝에 마크다운 요약 표.

## 출력
- 자유 서술 + 표 → `state.news_report`
- 하위의 Bull/Bear, 리스크 3인 프롬프트에는 "Latest world affairs news/report"라는 라벨로 들어간다.

## 설계 포인트
- 프롬프트가 짧은 대신 **도구 설명에 사용 예시 값을 넣어** 모델이 도구를 제대로 고르게 한다.
- 예측시장은 "live" 데이터라 과거 날짜 실행에서는 시점 일치가 보장되지 않는다(도구 측 `trade_date`로 일부 통제).
