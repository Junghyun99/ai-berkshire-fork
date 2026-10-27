---
name: ta-sentiment-analyst
role: Sentiment Analyst (시장 심리 분석가)
description: "TradingAgents 분석가 팀. 미리 수집한 뉴스 헤드라인·StockTwits·Reddit 게시물로 최근 7일 시장 심리를 판정한다. 도구를 직접 호출하지 않는다."
model_tier: quick
tools: 없음 (노드가 사전 수집해 프롬프트에 삽입)
output: state.sentiment_report (SentimentReport 구조화 출력 → 마크다운 렌더)
source: tradingagents/agents/analysts/sentiment_analyst.py
---

# Sentiment Analyst — 시장 심리 분석가

## 역할 요약
- 세 출처를 교차해 **6단계 심리 밴드 + 0~10 점수 + 신뢰도**를 낸다.
- 출처별 성격을 구분한다. 뉴스는 사실·기관 시각, StockTwits는 빠른 개인 심리, Reddit은 커뮤니티 담론.
- **출처 간 괴리 자체를 신호로** 읽는다. 데이터가 빈약하면 신뢰도를 낮추고 명시한다.
- 가격 예측을 하지 않는다. "트레이더가 기본·기술 분석과 함께 저울질할 신호"로만 제시한다.

## 데이터 준비 (LLM 호출 전, 코드에서)
| 블록 | 출처 | 비고 |
|---|---|---|
| `news_block` | Yahoo Finance 뉴스 (`get_news`) | 최근 7일 |
| `stocktwits_block` | StockTwits 캐시태그 스트림, 최대 30개 | 사용자 태그 Bullish/Bearish 포함 |
| `reddit_block` | r/wallstreetbets, r/stocks, r/investing (코인은 코인 커뮤니티) | 추천수·댓글수 없음 |

- 모든 수집기는 실패해도 예외 대신 `<unavailable>` 같은 자리표시 문자열을 돌려준다. LLM은 항상 무언가를 받는다.
- 소셜 게시물은 분석 기간으로 잘라 과거 날짜 실행에 오늘 게시물이 섞이지 않게 한다(#1220). 다만 원천 피드가 최근 것만 제공하므로 **과거 실행의 심리 입력은 완전한 point-in-time이 아니다**(원본 주석이 인정).
- `TYPESAFE_API_KEY`가 있으면 Jev 분류기로 게시물을 먼저 걸러낸다 → [output-refinement.md](../output-refinement.md) §6.

## 시스템 프롬프트 껍데기
[shared-prompts.md](../shared-prompts.md) §1의 Sentiment 변형(도구 문구 없음 + `NO_EXTERNAL_TOOLS`).

## 역할 프롬프트 원문

`{character}`는 서브레딧 구성에 따라 바뀐다. 기본값은 `r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term`.

```text
You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — {subreddit_list} (past 7 days)
Community discussion, without vote or comment counts. Subreddit character matters ({character}).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone. A block headed "Screened by Jev" has had off-topic posts removed; its stance count is a classifier's read of every on-topic post fetched, labelled or not, of which the posts listed are a sample. Read it alongside the user tags.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Read Reddit posts for substance.** The feed carries no vote or comment counts, so judge a post by its body excerpt, not its title alone, and do not infer engagement.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this explicitly in the `confidence` field and the narrative. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

{language_instruction}
```

## 핵심 지시 (한국어 요약)
1. StockTwits 강세:약세 비율 해석 기준 — 70/30 다소 강세, **90/10 이상은 과열·역발상 위험**, 50/50 불확실. 비율보다 **표본 수**가 중요.
2. 출처 간 괴리(뉴스는 약세인데 개인은 강세 등)는 그 자체로 신호.
3. Reddit은 추천수가 없으니 제목이 아닌 본문으로 판단하고, 반응 규모를 추정하지 말 것.
4. **사건(이벤트)과 의견을 구분**해 가중치를 다르게.
5. 반복 등장하는 서사(내러티브)를 찾을 것.
6. 데이터 한계를 `confidence`와 본문에 명시.
7. 촉매·리스크 식별. 8. 과거 심리는 예측력이 없다 — 가격 콜 금지.

## 출력 — `SentimentReport`
| 필드 | 타입 | 규칙 |
|---|---|---|
| `overall_band` | enum 6단계 | Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. 방향이 갈리면 Mixed, 전부 침묵일 때만 Neutral |
| `overall_score` | float 0~10 | 권장 대응: Bullish 6.5–10, Mildly Bullish 5.5–6.4, Neutral/Mixed 4.5–5.5, Mildly Bearish 3.5–4.4, Bearish 0–3.4 (강제되는 건 0~10 범위뿐) |
| `confidence` | low / medium / high | 출처 하나라도 자리표시이거나 데이터 5개 미만이면 low, 희박하면 medium, 세 출처 모두 실질 데이터면 high |
| `narrative` | str | ①출처별 분석(개수·비율·인용) ②괴리/일치 ③지배 서사 ④촉매·리스크 ⑤요약 표 |

렌더링 결과(저장되는 마크다운):
```text
**Overall Sentiment:** **{band}** (Score: {score:.1f}/10)
**Confidence:** {Confidence}

{narrative}
```

## 설계 포인트
- 원래는 자유 서술이었으나, 대시보드·로그가 정규식으로 밴드를 긁어내다 모델 버전마다 깨지는 문제 때문에 구조화 출력으로 바꿨다(스키마 주석).
- 데이터를 도구 호출로 가져오게 하지 않고 **프롬프트에 직접 삽입**한 이유: 모델이 게시물을 지어내는 것을 막고, 존재하지 않는 도구를 부르는 환각을 없애기 위해(#1130).
