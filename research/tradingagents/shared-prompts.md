# 공유 프롬프트 조각

여러 에이전트 프롬프트에 끼워 넣는 공통 문구. 출처: `tradingagents/agents/context.py`, `agents/structured.py`, `agents/analysts/turn.py`.

---

## 1. 도구형 애널리스트 공통 시스템 프롬프트

Market / News / Fundamentals 애널리스트가 같은 껍데기를 쓰고, `{system_message}`에 역할별 지시가 들어간다.

```text
You are a helpful AI assistant, collaborating with other assistants. Use the provided tools to progress towards answering the question. If you are unable to fully answer, that's OK; another assistant with different tools will help where you left off. Execute what you can to make progress. Report what your tools support; another agent decides the trade. You have access to the following tools: {tool_names}. Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}
{system_message}
```

- "Report what your tools support; another agent decides the trade." — 애널리스트가 매매 결론을 내지 못하게 역할 경계를 긋는다.
- `current_date`를 "지금"으로 간주시켜, 백테스트 시 모델이 실제 오늘 날짜로 도구를 호출하지 않게 한다.

Sentiment Analyst는 데이터를 미리 넣어 주므로 도구 문구를 빼고 아래 형태를 쓴다(도구 언급이 오히려 도구 호출 환각을 부른다는 이유, #1130).

```text
You are a helpful AI assistant, collaborating with other assistants. Report what your tools support; another agent decides the trade. Today's date is {current_date}; treat it as 'now' for all analysis. {instrument_context} {NO_EXTERNAL_TOOLS}
{system_message}
```

## 2. 도구 라운드 소진 시 마무리 지시 (`WRAP_UP`)

```text
You have used every tool round this report allows. Write your final report now from the tool results above, and say which data you could not retrieve.
```

- 기본 `max_tool_rounds = 20`. 소진하면 도구를 바인딩하지 않은 채 이 문구로 보고서를 쓰게 한다.
- 이때 `{tool_names}`는 `"none; your tool rounds are spent"`로 바뀌고, 이전 도구 호출/결과는 일반 텍스트 메시지로 풀어서 넘긴다(일부 제공사가 도구 미바인딩 상태의 tool-call 이력을 거부하기 때문).

## 3. 외부 도구 금지 (`NO_EXTERNAL_TOOLS`)

판단형 에이전트(Sentiment, Research Manager, Trader, PM)에 붙는다.

```text
Use only the evidence provided in this prompt. Do not call external tools or search the web; if something is missing, say so explicitly.
```

구조화 출력은 "스키마 하나"를 도구로 바인딩하는 방식이라, 모델이 검색 도구를 부르려 하면 구조화 호출 전체가 실패한다. 그래서 프롬프트로도 명시한다.

## 4. 출력 언어 지시 (`get_language_instruction`)

`output_language`가 영어면 빈 문자열(토큰 절약). 그 외에는:

```text
 Write your entire response in {lang}, except the labelled lines the format asks for (the "**Rating**:" line, "FINAL TRANSACTION PROPOSAL:"): keep their label and value in English, exactly as specified.
```

프로그램이 정규식으로 읽는 줄은 번역하지 않는다. 번역하면 "Sell은 아니다" 같은 부정문이 등급으로 오독될 수 있다(#1435).

## 5. 종목 식별 컨텍스트 (`build_instrument_context`)

모든 에이전트에 `{instrument_context}`로 들어간다.

```text
The instrument to analyze is `{ticker}`. The tools serve this instrument; refer to it by this exact ticker in every report and recommendation, preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`).
```

yfinance로 회사 정보를 얻으면 이어 붙인다.

- **현재 날짜 실행:** `Resolved identity: Company: {name}; Business classification: {sector} / {industry}; Exchange: {exchange}.`
- **과거 날짜 실행:** `Company: {name} (its current name, given only to identify it; on {trade_date} it may have been named differently)` — 섹터·거래소는 빼고 이름만. 오늘의 분류가 그 시점에도 맞았다는 보장이 없기 때문.
- 공통 후미: `Do not substitute a different company or ticker unless a tool result explicitly disproves this resolved identity.`
- 암호화폐: `Treat it as a crypto asset rather than a company, and do not assume company fundamentals are available.`

도입 배경(#814): 회사명을 주지 않으면 Market Analyst가 차트 모양만 보고 엉뚱한 업종의 회사로 착각하고, 그 오류가 하위 에이전트 전체로 번졌다.

## 6. 상대 발언이 없을 때 (`opponent_argument_or_opening`)

토론 첫 발언자에게 빈 문자열 대신 넣는다.

```text
(The {opponent} has not spoken yet — open the debate with your own case.)
```

빈 값을 "상대 주장을 반박하라" 프롬프트에 넣으면 모델이 상대 주장을 지어낸다(#1176).

## 7. 리포트가 없을 때 (`report_or_absent`)

```text
(No {source} report in this run: it is not available, not an empty finding.)
```

애널리스트를 선택하지 않았거나 실패한 경우. "결과 없음"과 "분석 안 함"을 구분시킨다.

## 8. 포트폴리오 컨텍스트가 없을 때 (`get_portfolio_context_from_state`)

Trader, 리스크 3인, PM에 들어간다.

```text
Portfolio context: not provided. You do not know the caller's current holdings or cash, so do not assume a flat book; give direction and sizing guidance in terms the caller can apply to their own position.
```

보유 정보가 없을 때 "무포지션"으로 가정하고 사이징하지 않게 막는다.

---

## 시사점 (이 저장소에 응용한다면)

- 6·7·8번 패턴은 investment-team 같은 병렬 스킬에서 "데이터 부족" 원칙(CLAUDE.md)을 프롬프트 수준에서 강제하는 방법으로 그대로 차용 가능하다.
- 4번은 한국어 보고서에서 ★ 점수나 결론 라벨을 기계가 읽어야 할 때(예: 스크리닝 결과 집계) 라벨만 고정하는 방식으로 응용할 수 있다.
