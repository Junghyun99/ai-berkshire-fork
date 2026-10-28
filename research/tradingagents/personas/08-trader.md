---
name: ta-trader
role: Trader (트레이더)
description: "TradingAgents 트레이더. Research Manager의 투자 계획을 구체적 거래안(Buy/Hold/Sell, 진입가, 손절가, 사이징)으로 바꾼다."
model_tier: quick
tools: 없음 (NO_EXTERNAL_TOOLS)
output: state.trader_investment_plan (TraderProposal 구조화 출력 → 마크다운 렌더)
source: tradingagents/agents/trader/trader.py
---

# Trader — 트레이더

## 역할 요약
- 투자 계획의 **방향**은 Research Manager에게서, **가격 수준**은 기술적 리포트에서 가져와 거래안을 만든다.
- 5단계 등급을 **3단계 행동**(Buy/Hold/Sell)으로 압축한다. Overweight → Buy, Underweight → Sell.
- 진입가·손절가는 **절대 가격**으로만 쓴다(퍼센트, 범위 금지).

## 입력
| 변수 | 출처 |
|---|---|
| `company_name` | `state.company_of_interest` |
| `instrument_context` | 종목 식별 |
| `investment_plan` | Research Manager 출력 |
| `market_report` | Market Analyst 리포트 — **있을 때만** 넣는다 |
| `portfolio_context` | 보유 현황, 없으면 "미제공" 표식 ([shared-prompts.md](../shared-prompts.md) §8) |

투자 계획은 토론을 요약하면서 정확한 가격 구조를 잃는다. 그래서 기술적 리포트를 따로 한 번 더 넣는다(#1167).

## 프롬프트 원문

**system** (`{grounding}`은 `market_report`가 있을 때만 들어간다)
```text
You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation to buy, sell, or hold. {grounding}State entry price and stop-loss as absolute price levels in the instrument's quote currency (for example 189.5), never a percentage or a range; convert a percentage distance to the price level it implies, or omit the field if you cannot state a number. Use only the evidence provided in this prompt. Do not call external tools or search the web; if something is missing, say so explicitly.{language_instruction}
```

`{grounding}`:
```text
Ground concrete price levels (entry, stop-loss, position sizing) in the technical market report's price structure -- current price, support/resistance, ATR, and volatility -- and use the research plan for direction and strategy. 
```

**user**
```text
Here is the research team's investment plan for {company_name}. {instrument_context}

Technical Market Report:
{market_report}

{portfolio_context}

Proposed Investment Plan:
{investment_plan}

Make an informed, strategic trading decision.

## Output

Write these sections, in this order, starting with the action on its own line:

- **Action**: exactly one of Buy / Hold / Sell. A research recommendation of Overweight is a Buy and Underweight is a Sell, sized by how strong the case is; conflict alone is not a Hold.
- **Reasoning**: why, against the plan and the price structure
- **Entry Price**, **Stop Loss**, **Position Sizing**: when you can state them
```
(`market_report`가 비면 `Technical Market Report:` 블록 전체가 빠진다.)

## 핵심 지시 (한국어 요약)
1. 방향과 전략은 투자 계획에서, 진입·손절·사이징 같은 **가격 수준은 기술적 리포트의 현재가·지지/저항·ATR·변동성**에서.
2. 진입가·손절가는 호가 통화 기준 **절대 가격**(예: 189.5). 퍼센트나 범위 금지. 퍼센트 거리는 가격으로 환산하거나, 숫자를 못 대면 생략.
3. Overweight는 Buy, Underweight는 Sell. 충돌만으로 Hold 금지.

## 출력 — `TraderProposal`
| 필드 | 타입 | 규칙 |
|---|---|---|
| `action` | `TraderAction` (Buy/Hold/Sell) | 필수 |
| `reasoning` | str | 분석 리포트와 투자 계획에 근거, 2~4문장 |
| `entry_price` | float \| None | 절대 가격. 퍼센트·범위 금지, 모르면 생략 |
| `stop_loss` | float \| None | 절대 가격. 퍼센트는 가격으로 환산 |
| `position_sizing` | str \| None | 예: "5% of portfolio" |

`entry_price`/`stop_loss`는 검증 전에 정제된다(`"15%"` → None, `"$1,234.50"` → 1234.5 등). → [output-refinement.md](../output-refinement.md) §3

렌더링 결과:
```text
**Action**: {Action}

**Reasoning**: {reasoning}

**Entry Price**: {entry_price | not provided}

**Stop Loss**: {stop_loss | not provided}

**Position Sizing**: {position_sizing | not provided}

FINAL TRANSACTION PROPOSAL: **{BUY|HOLD|SELL}**
```

## 설계 포인트
- 5단계 → 3단계 압축은 의도적이다. "Trader는 이번 라운드에 실행할지 말지만, 비중의 미세 조정은 PM이"라는 역할 분리(`TraderAction` 주석).
- 퍼센트 금지 규칙은 실제 사고에서 나왔다. 모델이 손절가에 `"15%"`를 쓰면 숫자 15로 읽혀 600달러 주식의 손절가가 15달러가 될 수 있다(#1288).
- 마지막 `FINAL TRANSACTION PROPOSAL:` 줄은 외부 코드가 grep하는 호환용이라 언어 설정과 무관하게 영어로 고정.
- 자동매매에 연결한다면 **이 출력이 주문 생성에 가장 가까운 지점**이다. 단, 수량·체결·현금 원장은 원본 프로젝트가 의도적으로 구현하지 않았다.
