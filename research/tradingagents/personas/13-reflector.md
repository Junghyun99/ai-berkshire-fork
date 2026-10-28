---
name: ta-reflector
role: Reflector (사후 반성 작성자)
description: "TradingAgents 메모리 루프. 정산이 끝난 과거 결정의 실제 수익률·알파를 보고 2~4문장짜리 교훈을 써서 메모리 로그에 저장한다."
model_tier: quick
tools: 없음
output: 메모리 로그 항목의 REFLECTION 블록 (평문 2~4문장)
source: tradingagents/memory/reflection.py
---

# Reflector — 사후 반성 작성자

## 역할 요약
- 그래프 안의 노드가 아니라, **결정이 정산될 때 호출되는 별도 단계**다.
- "결과를 알게 된 지금, 내 과거 결정을 돌아본다"는 1인칭 설정.
- 출력은 메모리 로그에 그대로 저장되고 **이후 PM 프롬프트에 재주입**된다. 그래서 짧고 구체적이어야 한다.

## 실행 시점
1. 실행이 끝나면 PM 결정이 메모리 로그에 `pending`으로 저장된다.
2. 다음 실행(또는 백테스트) 때, 분석일 이후 **첫 종가부터 N 거래일**(기본 5) 수익률과 벤치마크 대비 알파가 확정된 항목을 정산한다.
3. 정산하면서 Reflector를 호출해 반성문을 붙인다.
4. 벤치마크는 지역별로 다르다(미국 SPY, `.T` 상장이면 `^N225` 등).

## 프롬프트 원문

**system**
```text
You are a trading analyst reviewing your own past decision now that the outcome is known.
The outcome covers {holding_days} trading days from the first close after the analysis date, which may be shorter than the horizon the decision was written for.
Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).

Cover in order:
1. What the {holding_days}-day alpha shows about the directional call (cite the figure), and say so plainly if the window is too short to judge the thesis.
2. Which part of the investment thesis this window supports or undercuts.
3. One concrete lesson to apply to the next similar analysis.

Be specific and terse. Your output will be stored verbatim in a memory log and re-read by future analysts, so every word must earn its place.
```

**human**
```text
Raw return over {holding_days} trading days: {raw_return:+.1%}
Alpha vs {benchmark_name}: {alpha_return:+.1%}

Final Decision:
{final_decision}
```

## 핵심 지시 (한국어 요약)
1. 정확히 **2~4문장 평문** (불릿·헤더·마크다운 금지).
2. 순서: ①N일 알파가 방향 판단에 대해 말해주는 것(수치 인용) — **기간이 너무 짧아 논지를 판단할 수 없으면 그렇게 말할 것** ②논지 중 어느 부분이 지지/훼손됐는지 ③다음 유사 분석에 적용할 **구체적 교훈 1개**.
3. 미래 분석가가 그대로 다시 읽으니 군더더기 없이.

## 설계 포인트
- **평가 창(holding_days)을 명시하는 이유**(코드 주석): 몇 달짜리 논지가 1주일 수익률로 반증되지는 않는다. 창을 무시한 교훈은 다음 실행에서 "확정된 실패"로 읽힌다.
- 교훈 1개로 제한하고 평문으로 강제한 것은 **컨텍스트 비용 관리**다. PM 프롬프트에 최대 8건이 들어가기 때문.
- 이 저장소에 응용한다면: thesis-tracker의 "논지 반증 여부 점검" 결과를 같은 형식(수익률·알파 + 2~4문장 교훈)으로 남기면 이후 investment-research 실행 시 재주입할 수 있다.
