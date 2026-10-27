# TradingAgents 페르소나·프롬프트 연구 노트

> **연구용 자료.** `.claude/agents/`가 아니라 이 디렉토리에 두었으므로 Claude Code가 자동 로드하지 않는다.
> 실제 서브에이전트로 쓰려면 별도로 `.claude/agents/`로 옮기고 도구·출력 형식을 이 저장소 규칙에 맞게 다시 써야 한다.

## 출처

| 항목 | 값 |
|---|---|
| 저장소 | https://github.com/TauricResearch/TradingAgents |
| 기준 커밋 | `c4544913a14ed3df5f1ed7b9e8483270ce20682a` (2026-10-27, v0.7.1 이후) |
| 라이선스 | Apache License 2.0 — 프롬프트 원문 인용 시 출처 표기 유지 |
| 논문 | arXiv 2412.20138 |

프롬프트 원문은 영어 그대로 옮겼다(`{...}`는 런타임에 채워지는 변수). 각 파일의 한국어 부분은 요약·해설이다.
본문에 나오는 `#1176` 같은 번호는 원본 저장소의 이슈/PR 번호로, 코드 주석에 근거로 달려 있던 것이다.

## 파이프라인

```
                 ┌─ 01 Market Analyst ───────┐
 [분석가, 병렬] ─┼─ 02 Sentiment Analyst ────┤   (quick 모델, 도구 사용)
                 ├─ 03 News Analyst ─────────┤
                 └─ 04 Fundamentals Analyst ─┘
                              ↓ 4개 리포트
 [투자 토론]     05 Bull ⇄ 06 Bear  (max_debate_rounds × 2회 발언)
                              ↓
                 07 Research Manager  (deep 모델) → ResearchPlan (5단계 등급)
                              ↓
                 08 Trader (quick) → TraderProposal (Buy/Hold/Sell + 진입가·손절가)
                              ↓
 [리스크 토론]   09 Aggressive → 10 Conservative → 11 Neutral  (max_risk_discuss_rounds × 3회)
                              ↓
                 12 Portfolio Manager (deep) → PortfolioDecision = 최종 등급
                              ↓
                 메모리 로그 저장 → (N 거래일 후) 수익률 정산 → 13 Reflector가 교훈 작성
                              ↺ 다음 실행 때 PM 프롬프트에 past_context로 재주입
```

- 토론 순서 규칙(`graph/conditional_logic.py`): 투자 토론은 `count >= 2 × max_debate_rounds`이면 Research Manager로, 리스크 토론은 `count >= 3 × max_risk_discuss_rounds`이면 PM으로 넘어간다. 기본값은 둘 다 1라운드.
- 모델 티어(`graph/setup.py`): **deep = Research Manager, Portfolio Manager** / 나머지는 모두 **quick**. Reflector도 quick.

## 파일 목록

| 파일 | 역할 | 티어 | 출력 |
|---|---|---|---|
| [personas/01-market-analyst.md](personas/01-market-analyst.md) | 기술적 지표 분석 | quick | 자유 서술 + 표 |
| [personas/02-sentiment-analyst.md](personas/02-sentiment-analyst.md) | 뉴스·StockTwits·Reddit 심리 | quick | `SentimentReport` |
| [personas/03-news-analyst.md](personas/03-news-analyst.md) | 뉴스·거시·예측시장 | quick | 자유 서술 + 표 |
| [personas/04-fundamentals-analyst.md](personas/04-fundamentals-analyst.md) | 재무제표·내부자 거래 | quick | 자유 서술 + 표 |
| [personas/05-bull-researcher.md](personas/05-bull-researcher.md) | 강세 논거 | quick | 대화체 발언 |
| [personas/06-bear-researcher.md](personas/06-bear-researcher.md) | 약세 논거 | quick | 대화체 발언 |
| [personas/07-research-manager.md](personas/07-research-manager.md) | 투자 토론 심판 | **deep** | `ResearchPlan` |
| [personas/08-trader.md](personas/08-trader.md) | 거래안 작성 | quick | `TraderProposal` |
| [personas/09-aggressive-risk-analyst.md](personas/09-aggressive-risk-analyst.md) | 공격형 리스크 | quick | 대화체 발언 |
| [personas/10-conservative-risk-analyst.md](personas/10-conservative-risk-analyst.md) | 보수형 리스크 | quick | 대화체 발언 |
| [personas/11-neutral-risk-analyst.md](personas/11-neutral-risk-analyst.md) | 중립형 리스크 | quick | 대화체 발언 |
| [personas/12-portfolio-manager.md](personas/12-portfolio-manager.md) | 최종 결정 | **deep** | `PortfolioDecision` |
| [personas/13-reflector.md](personas/13-reflector.md) | 사후 반성(교훈) | quick | 2~4문장 |
| [shared-prompts.md](shared-prompts.md) | 모든 에이전트가 공유하는 프롬프트 조각 | — | — |
| [output-refinement.md](output-refinement.md) | 구조화 출력·폴백·등급 파싱·값 정제 | — | — |

## ai-berkshire 페르소나와의 대비

| | ai-berkshire (`.claude/agents/`) | TradingAgents |
|---|---|---|
| 페르소나 축 | 실존 투자자 철학 (버핏·멍거·돤융핑·리루) | 조직 직무 (애널리스트·트레이더·리스크·PM) |
| 시간 지평 | 장기 보유 | 단기~중기 매매 (리플렉션 기본 창 5거래일) |
| 상호작용 | 병렬 독립 분석 → Team Lead 종합 | 순차 토론(반박 강제) → 심판이 판정 |
| 출력 | 장문 보고서 | Pydantic 스키마 + 마크다운 렌더 |
| 정보 고정 | 사람 검수 | 프롬프트로 "도구 출력만 근거" 강제, 없는 데이터는 명시 |
| 피드백 | 없음 (thesis-tracker는 수동) | 정산된 수익률 → 반성문 → 다음 프롬프트 재주입 |

## 연구 관점에서 눈여겨볼 설계

1. **"충돌은 Hold의 이유가 아니다"** — Research Manager, Trader, PM 세 곳에 반복된다. LLM이 애매하면 Hold로 도망가는 경향을 프롬프트와 스키마 description 양쪽에서 막는다.
2. **빈 입력을 명시적 표식으로 치환** — 상대 발언이 없으면 "아직 말하지 않았다", 리포트가 없으면 "빈 결과가 아니라 미제공"이라고 넣는다. 빈 문자열이 환각을 부르는 것을 막는 장치. ([shared-prompts.md](shared-prompts.md))
3. **기계가 읽는 줄은 번역 금지** — 출력 언어를 바꿔도 `**Rating**:` 줄과 `FINAL TRANSACTION PROPOSAL:` 줄은 영어로 고정한다.
4. **판독 불가 = REVIEW, Hold 아님** — 등급을 못 읽으면 거래 가능한 신호로 위장하지 않는다. ([output-refinement.md](output-refinement.md))
5. **가격 필드 정제** — `"15%"`, `"150-160"`, `"N/A"` 같은 값은 필드 하나만 버리고 나머지 결정은 살린다.
6. **시점 고정(point-in-time)** — 과거 날짜 실행에서는 오늘 기준 섹터·거래소 정보를 주지 않고, 그 날짜 이후 확정된 교훈도 주입하지 않는다.
