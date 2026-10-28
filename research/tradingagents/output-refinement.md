# 출력 정제 (Output Refinement)

LLM 출력을 프로그램이 믿고 쓸 수 있는 값으로 바꾸는 장치들. 출처: `tradingagents/agents/schemas.py`, `structured.py`, `rating.py`, `post_screen.py`.

전체 흐름:

```
프롬프트 ─► [구조화 호출] with_structured_output(Schema)
              │ 성공 ─► Pydantic 검증 (값 정제 validator) ─► render_*() ─► 마크다운
              │ 실패/None
              ▼
           [자유 서술 재호출] llm.invoke(같은 프롬프트) ─► 텍스트 그대로
                                                         │ (PM만) parse_rating() ─► 등급 or REVIEW
```

---

## 1. 구조화 출력 적용 범위

| 에이전트 | 스키마 | 렌더 함수 | 실패 시 |
|---|---|---|---|
| Sentiment Analyst | `SentimentReport` | `render_sentiment_report` | 자유 서술 |
| Research Manager | `ResearchPlan` | `render_research_plan` | 자유 서술 |
| Trader | `TraderProposal` | `render_trader_proposal` | 자유 서술 |
| Portfolio Manager | `PortfolioDecision` | `render_pm_decision` | 자유 서술 + `parse_rating` |
| 나머지 (애널리스트 3, 토론자 5, Reflector) | 없음 | — | — |

원칙(스키마 모듈 주석):
- 시스템의 **1차 산출물은 여전히 산문**이다. 사람과 하위 에이전트가 읽는 것은 렌더링된 마크다운이다.
- 구조화 출력은 **결정을 내리는 에이전트에만** 얹는다. 목적은 ①실행·제공사가 달라도 섹션 헤더 통일 ②제공사 고유 구조화 모드 사용(OpenAI/xAI는 json_schema, Gemini는 response_schema, Anthropic은 tool-use) ③**필드 description이 곧 출력 지시**가 되어 프롬프트 본문은 맥락과 등급 기준에 집중 ④렌더 함수가 기존 마크다운 형태를 재현해 하위 코드는 바뀌지 않음.

## 2. 구조화 호출과 폴백 (`structured.py`)

```python
def bind_structured(llm, schema, agent_name):
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError):
        logger.warning("...falling back to free-text generation")
        return None            # 이 에이전트는 항상 자유 서술

def invoke_structured(structured_llm, prompt, agent_name):
    if structured_llm is None:
        return None
    try:
        result = structured_llm.invoke(prompt)
        if result is None:     # thinking 모델이 도구 대신 평문으로 답한 경우
            raise ValueError("structured output returned no parsed result")
        return result
    except Exception:
        logger.warning("...retrying once as free text")
        return None

def invoke_structured_or_freetext(structured_llm, plain_llm, prompt, render, agent_name):
    result = invoke_structured(structured_llm, prompt, agent_name)
    if result is not None:
        return render(result)
    return plain_llm.invoke(prompt).content
```

포인트:
- **두 단계 실패 지점**을 구분한다. 생성 시점에 바인딩이 안 되면 영구 자유 서술, 호출 시점에 깨지면 그 회만 재시도.
- `result is None` 처리: 추론(thinking) 모델은 스키마 도구를 호출하지 않고 텍스트로 답하기도 한다. 예외가 아니라 None이 나오므로 명시적으로 실패 처리한다.
- **재시도는 1회, 같은 프롬프트로.** 파이프라인이 멈추지 않는 것이 우선이다.
- 프롬프트에 `NO_EXTERNAL_TOOLS`를 넣는 이유: 스키마 자체가 유일한 바인딩 도구라, 모델이 검색 도구를 부르면 구조화 시도 전체가 버려진다(#1130).
- 그래서 프롬프트 본문에도 "Write these sections, in this order..."처럼 **자유 서술 폴백에서도 같은 모양이 나오도록** 섹션 지시를 중복해 둔다.

## 3. 숫자 필드 정제 (`_coerce_optional_float`)

Trader의 `entry_price`, `stop_loss`, PM의 `price_target`에 `mode="before"` validator로 적용.

```python
_NULLISH_FLOAT = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown"}

def _coerce_optional_float(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in _NULLISH_FLOAT or text.endswith("%"):
        return None
    cleaned = text.replace(",", "").lstrip("$€£¥").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
```

| LLM이 쓴 값 | 결과 | 이유 |
|---|---|---|
| `189.5`, `"189.5"` | 189.5 | 정상 |
| `"$1,234.50"` | 1234.5 | 통화기호·천단위 제거 |
| `"None"`, `"N/A"`, `"TBD"` | None | 자리표시 문자열 (#1058) |
| `"15%"` | None | **퍼센트는 가격으로 복원 불가.** 15로 읽으면 600달러 주식의 손절가가 15달러가 된다 (#1288) |
| `"150-160"`, `"around 150"` | None | 단일 숫자가 아님 |

핵심 원칙: **잘못된 필드 하나 때문에 결정 전체를 버리지 않는다.** 정제 없이 Pydantic 검증이 실패하면 action·reasoning처럼 제대로 된 필드까지 모두 날아가고 자유 서술 폴백으로 떨어진다.

## 4. 등급 추출 (`rating.py`)

자유 서술 폴백일 때 PM 결정문에서 5단계 등급을 읽는다. 메모리 로그 태그에도 쓴다.

### 상수
```python
RATINGS_5_TIER = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
RATING_REVIEW = "REVIEW"   # 판독 불가. 거래 가능한 신호가 아님
```

### 정규식
```python
# "Rating: X", "rating - X", "Rating — **X**" 형태. "rating"은 단어 시작이어야 함
# → "Operating margin: Sell-side"는 라벨이 아님
_RATING_LABEL_RE = re.compile(
    r"(?<![a-z])rating\b[^:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)", re.IGNORECASE)

# 결정 자신의 등급 줄: 리스트 기호·강조·헤딩 허용, "rating" 앞에는 자기 결정을 뜻하는 수식어만
# "Consensus rating: Buy", "Trader's rating: Buy"는 남의 등급이므로 제외
_OWN_QUALIFIER = r"(?:(?:final|our|overall|my|recommended|updated|revised|new|current)\s+)*"
_RATING_LINE_RE = re.compile(
    r"\s*(?P<item>(?:[-+*\u2022]|\d+[.)])\s+)?[\s*_#]*" + _OWN_QUALIFIER
    + r"rating[^\w:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(?P<value>\w+)", re.IGNORECASE)

# 등급 '범례'를 반복한 줄은 결정이 아님: "Rating Scale: Buy, ..."
_RATING_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)
```

### 판정 알고리즘 (`extract_rating`)
1. 텍스트를 **NFKC 정규화** (`Rating：Overweight`처럼 전각 콜론도 ASCII와 동일하게).
2. 빈 줄과 **범례 줄**(`Rating Scale: ...`)을 제외.
3. **첫 줄**(헤딩 제외)이 등급 줄 형태이고 리스트 항목이 아니면 → 즉시 그 등급 반환. 프롬프트가 "등급으로 시작하라"고 지시했기 때문.
4. 아니면 후보 수집:
   - `own`: 리스트 항목이 아닌 자기 등급 줄들 (+ 첫 줄이 리스트 항목인 등급 줄이었다면 포함)
   - `labels`: 텍스트 전체의 모든 `rating: X` 라벨
5. `own`이 있으면 `own`, 없으면 `labels`를 쓰되 **모든 후보가 같은 등급일 때만** 반환. 서로 다르면 None.
6. **라벨 없는 산문 속 등급 단어는 읽지 않는다.** "이건 Sell이 아니다"를 Sell로 오독하지 않기 위함.

```python
def parse_rating(text, default=RATING_REVIEW):
    rating = extract_rating(text)
    return rating if rating is not None else default
```

### 왜 Hold가 아니라 REVIEW인가 (#1170)
- 판독 불가 결정을 Hold로 기록하면, 그 Hold가 **다음 실행의 past_context로 재주입**돼 "내린 적 없는 판단"이 교훈처럼 인용된다.
- 백테스트 채점에서도 REVIEW는 거래 신호에서 제외해야 한다(`is_review()`로 가드).

### PM의 등급 확정 우선순위
```python
decision = invoke_structured(structured_llm, prompt, "Portfolio Manager")
if decision is not None:
    final_trade_decision = render_pm_decision(decision)
    final_rating = decision.rating.value          # 타입이 있는 값이 곧 결정
else:
    final_trade_decision = llm.invoke(prompt).content
    final_rating = parse_rating(final_trade_decision)   # 실패하면 "REVIEW"
```
구조화 성공 시 렌더된 텍스트를 다시 파싱하지 않는다. thesis 본문이 다른 등급을 인용하면 그것이 결정을 덮을 수 있기 때문이다.

## 5. 렌더링 규칙

| 규칙 | 예 | 이유 |
|---|---|---|
| 첫 줄은 결정 라벨 | `**Rating**: Buy`, `**Action**: Buy`, `**Recommendation**: Hold` | 파서가 첫 줄을 우선 판독 |
| 선택 필드도 항상 출력 | `**Stop Loss**: not provided` | "제시하지 않음"과 "묻지 않음"을 구분 |
| 호환용 꼬리 줄 | `FINAL TRANSACTION PROPOSAL: **BUY**` | 외부 코드가 grep |
| 라벨 줄은 번역 금지 | 출력 언어가 한국어여도 `**Rating**: Buy` 유지 | 부정문 오독 방지 (#1435) |
| 심리 헤더 결정론적 생성 | `**Overall Sentiment:** **Mixed** (Score: 5.0/10)` | 정규식 없이 대시보드가 읽음 |

## 6. 소셜 게시물 사전 정제 (`post_screen.py`, 선택 기능)

`TYPESAFE_API_KEY`가 있을 때만 동작. LLM에 넣기 **전에** 입력을 정제하는 단계다.

- 게시물마다 분류기(Jev)에 두 질문:
  - `about`: 이 게시물이 해당 종목(회사·주식·제품·전망)에 관한 것인가? — 지나가듯 언급, 티커 나열, 스팸/홍보, 다른 회사면 false
  - `stance`: 작성자가 주가를 어떻게 보나? bullish / bearish / neutral(질문, 의견 없는 뉴스, 남의 견해 인용)
- 임계값:
  - `about` 확률 < **0.3**이면 제거 (애매한 중간은 남김)
  - `stance` 신뢰도 < **0.5**이면 `unclear`
- 블록 맨 위에 요약 줄 삽입:
  ```text
  Screened by Jev: {kept} of the {total} posts fetched are about {instrument}; their stance on its stock: {n} bullish, {n} bearish, {n} neutral, {n} unclear.
  ```
- 실패 시 전부 유지하고 `<Jev screening unavailable ({reason}); posts are unscreened>` 표시. 429/529와 연결 오류는 백오프 재시도(최대 3회, `Retry-After` 준수, 최대 30초).

## 7. 그 밖의 입력 정제 (프롬프트 쪽)

출력 정제와 짝을 이루는 입력 측 장치. 상세는 [shared-prompts.md](shared-prompts.md).
- 빈 상대 발언 → "아직 말하지 않았다" 표식
- 빈 리포트 → "미제공, 빈 결과 아님" 표식
- 보유 정보 없음 → "무포지션으로 가정하지 말 것"
- 과거 날짜 실행 → 오늘 기준 섹터·거래소 정보 제거, 그 날짜 이후 확정된 교훈 제외

---

## 이 저장소에 응용할 때의 체크리스트 (연구 메모)

- [ ] 결론 라벨(예: `**종합 판단**: 매수 검토`, ★ 점수)을 **첫 줄 고정 + 라벨 고정**으로 쓰면 스크리닝 결과를 기계적으로 집계할 수 있다.
- [ ] 라벨을 못 읽으면 "보류"로 채우지 말고 별도 표식(REVIEW)으로 남긴다.
- [ ] 목표가·안전마진 가격 같은 숫자 필드는 퍼센트·범위·"약 ~원"을 허용하지 않고, 정제 실패 시 그 필드만 비운다.
- [ ] 선택 항목은 비어도 "미제공"으로 출력해 누락과 미요청을 구분한다.
- [ ] Python 쪽에서 쓴다면 `tools/`에 Pydantic 스키마 + `_coerce_optional_float` 류 validator를 두고, Claude Code 스킬에서는 같은 규칙을 출력 형식 지시로 옮긴다.
