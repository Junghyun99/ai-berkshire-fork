---
name: ta-portfolio-manager
role: Portfolio Manager (포트폴리오 매니저 · 최종 결정권자)
description: "TradingAgents 최종 결정권자. 리스크 토론, 투자 계획, 거래안, 보유 현황, 과거 교훈을 종합해 5단계 최종 등급과 실행 요약을 낸다."
model_tier: deep
tools: 없음 (NO_EXTERNAL_TOOLS)
output: state.final_trade_decision (마크다운), state.final_rating (등급 문자열)
source: tradingagents/agents/managers/portfolio_manager.py
---

# Portfolio Manager — 최종 결정권자

## 역할 요약
- 리스크 분석가 3인의 토론을 종합해 **실행할 최종 결정**을 내린다.
- 이 등급이 실행 전체의 `final_rating`이 되고, 메모리 로그에 저장돼 **나중에 실제 수익률로 채점**된다.
- 유일하게 **과거 결정의 교훈(`past_context`)** 을 입력으로 받는 에이전트다.
- **deep 모델** 사용.

## 입력
| 변수 | 출처 |
|---|---|
| `instrument_context` | 종목 식별 |
| `portfolio_context` | 보유 현황, 없으면 "미제공" 표식 |
| `research_plan` | `state.investment_plan` (Research Manager) |
| `trader_plan` | `state.trader_investment_plan` (Trader) |
| `past_context` | 메모리 로그에서 생성한 과거 교훈 (아래 참고). 없으면 줄 자체가 빠진다 |
| `history` | `risk_debate_state.history` (리스크 토론 전체) |

### `past_context` 구성 (`memory/log.py` `get_past_context`)
- **같은 종목** 최근 5건(`n_same`): 결정 전문 + 반성문
- **다른 종목** 최근 3건(`n_cross`): 반성문만 (없으면 결정문 앞 300자)
- 정산이 끝난(수익률이 확정된) 기록만 포함. 과거 날짜 실행에서는 **그 날짜 이전에 확정된 교훈만** 넣는다(#1251, 미래 정보 유출 방지).
- 각 기록 태그 형식: `[날짜 | 종목 | 등급 | 원수익률 | 알파 | 보유일수]`

```text
Past analyses of {ticker} (most recent first):

[2026-09-01 | NVDA | Overweight | +3.2% | +1.1% | 5]

DECISION:
...

REFLECTION:
...

Recent cross-ticker lessons:

[2026-08-20 | AAPL | Hold | -0.8%]
...
```

## 프롬프트 원문

```text
As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

{portfolio_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
- Lessons from prior decisions and outcomes:
{past_context}

**Risk Analysts Debate History:**
{history}

---

Ground every conclusion in specific evidence from the analysts. The risk debate always contains conflicting stances; deciding which is stronger is the job, so conflict alone is not a reason to Hold. Commit to the stronger case, sized by how decisively it wins. Choose Hold only when the evidence is still balanced after that weighing, or too thin to support a call; do not force a direction to appear decisive. Weigh the analysts on their merits, independent of speaking order.

## Output

Write these sections, in this order, starting with the rating on its own line:

- **Rating**: exactly one of Buy / Overweight / Hold / Underweight / Sell
- **Executive Summary**: the call and how to act on it
- **Investment Thesis**: the evidence that decided it, and what would change it

Use only the evidence provided in this prompt. Do not call external tools or search the web; if something is missing, say so explicitly.{language_instruction}
```

## 핵심 지시 (한국어 요약)
| 등급 | PM 기준 의미 (Research Manager와 표현이 조금 다름) |
|---|---|
| **Buy** | 진입 또는 추가에 강한 확신 |
| **Overweight** | 우호적, 비중 점진 확대 |
| **Hold** | 현 포지션 유지, 조치 불필요 |
| **Underweight** | 비중 축소, 일부 차익 실현 |
| **Sell** | 청산 또는 진입 회피 |

1. 모든 결론을 애널리스트의 **구체적 증거**에 근거.
2. 충돌만으로 Hold 금지, 더 강한 쪽에 확신 정도만큼 걸 것.
3. 방향을 억지로 만들지도 말 것. 발언 순서와 무관하게 평가.
4. 출력 첫 줄은 반드시 등급. Investment Thesis에는 **"무엇이 바뀌면 판단이 바뀌는지"** 를 포함.

## 출력 — `PortfolioDecision`
| 필드 | 타입 | 스키마 description 요지 |
|---|---|---|
| `rating` | `PortfolioRating` (5단계) | 판정 규칙 반복 |
| `executive_summary` | str | 진입 전략, 사이징, 핵심 위험 가격대, 시간 지평. 2~4문장 |
| `investment_thesis` | str | 토론의 구체적 증거에 근거한 상세 논리. 과거 교훈이 주어지면 반영, 없으면 현재 분석만 |
| `price_target` | float \| None | 목표가 (호가 통화). 정제 규칙 적용 |
| `time_horizon` | str \| None | 권장 보유 기간, 예: "3-6 months" |

렌더링 결과:
```text
**Rating**: {Rating}

**Executive Summary**: {executive_summary}

**Investment Thesis**: {investment_thesis}

**Price Target**: {price_target | not provided}

**Time Horizon**: {time_horizon | not provided}
```

### 등급 확정 방식 (다른 에이전트와 다른 점)
- 구조화 호출이 성공하면 **스키마의 `rating` 필드 값이 곧 결정**이다. 렌더링된 텍스트에서 다시 읽지 않는다. 본문(thesis)이 다른 등급을 인용하면 그게 결정을 덮어쓸 수 있기 때문(코드 주석).
- 실패하면 자유 서술로 받고 `parse_rating()`으로 등급을 추출한다. 못 읽으면 **`REVIEW`** (거래 불가 신호). → [output-refinement.md](../output-refinement.md) §4

## 설계 포인트
- Research Manager는 "토론 → 계획", PM은 "계획 + 거래안 + 위험 토론 + 보유 현황 + 과거 교훈 → 최종 결정". 위계가 분명하다.
- 과거 교훈 재주입은 **학습 없이 프롬프트만으로 하는 강화 루프**다. 이 저장소의 thesis-tracker를 자동화한다면 가장 참고할 만한 부분.
