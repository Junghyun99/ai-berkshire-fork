# Phase 0-2 — 기금운용 아키텍처 및 의사결정 계약 (설계 초안)

- 작성일: 2026-10-28
- 상태: **설계 초안 / Skill 및 실행 코드 변경 없음**
- 전제: Phase 0-1 현황 분석(PR #23) 및 국민연금 프로세스 연구(PR #17)를 참조한다. 두 PR이 아직 병합되지 않았어도 이 문서는 독립적으로 검토할 수 있다.
- 범위: **Investment Policy**, **의사결정 권한**, **단계 간 데이터 계약**, **기존 Skill 호환성**, **수용 기준**.
- 목적: 기존 AI Berkshire의 19개 Skill을 폐기하지 않고 Plan → Do → See로 연결한다. 국민연금 내부 업무흐름을 그대로 복제한다는 뜻은 아니다.

## 1. 설계 원칙과 비목표

1. **정책이 연구 의견보다 상위**다. 개별 분석 Skill의 비중·현금·레버리지 기본값은 승인된 정책을 덮을 수 없다.
2. **조사·투자 의견·포트폴리오 제안·승인·주문을 분리**한다. 자연어 `매수`는 체결이나 승인 기록이 아니다.
3. **LLM은 가설과 대안을 생성**하고, 숫자 계산·한도 위반 판정·상태 전이·승인 여부는 결정론적 코드가 담당한다.
4. 모든 판단에는 **데이터 기준 시점과 출처**, **Skill/모델/정책 버전**, **반증 조건**을 연결한다.
5. 동일한 데이터 계약으로 클라우드 및 로컬 LLM을 교체할 수 있도록 한다.
6. 기존 `decision-ledger`, `position_plan.py`, `report_check.py`의 라벨/파싱 형식은 이 단계에서 변경하지 않는다.
7. **모르는 것은 보류**한다. 입력 불충분·기준시점 불일치·정책 불명확 시 자동 승인하지 않는다.

**비목표:** 주문 API 통합, 실제 계좌 연결, 투자 비율의 특정 값 결정, 완전 자율매매, 기존 보고서 일괄 수정, 신규 Skill 즉시 추가.

## 2. 도메인 경계: Plan / Do / See

```text
Plan: InvestmentPolicy (승인·버전 관리)
       ├─ StrategicAllocation (장기 목표, 허용 편차)
       └─ TacticalOverlay (허용 범위 내 단기 제안)
                  │
                  ▼
Do: Universe/Screen → ResearchOpinion → PortfolioProposal
                                           │
                                           ▼
                                  Policy/Risk Validation
                                           │
                                           ▼
                                    ApprovalDecision
                                           │
                                           ▼
                                    ExecutionRecord*
                  │
                  ▼
See: Thesis Monitoring + Portfolio Risk → Idea Evaluation
                                         → Portfolio Performance
                                         → Policy/Skill Improvement Proposal
```

`*ExecutionRecord`는 **미래를 위한 계약 자리**일 뿐, 현재 단계에 자동 주문 기능을 추가하지 않는다.

### 책임/권한 매트릭스

| 주체/계층 | 생성 가능 | 승인 가능 | 절대 해서는 안 되는 일 |
| --- | --- | --- | --- |
| 정책 설계 Agent | 투자정책 후보, 위험/목표 시나리오 | 아니오 | 사용자의 목표·한도를 묵시적으로 확정 |
| 사용자(정책 소유자) | 정책 승인/수정/폐기 | **투자정책, 투자 제안, 주문** | 해당 없음 |
| 기업 리서치 Skill | 재무·산업 분석, `ResearchOpinion` | 아니오 | 매수 의견을 체결로 기록 |
| 포트폴리오 판단 계층 | `PortfolioProposal`, 리스크 분석 | 아니오 | 정책 초과 편입을 승인으로 간주 |
| Policy/Risk Validator (코드) | 적합/위반/불충분 판정 | 아니오 | 근거 부족 시 임의로 예외 승인 |
| 승인 게이트 (코드 + 사용자 행위) | `ApprovalDecision`의 감사 기록 | **사용자 명시 승인만 수용** | LLM 텍스트를 명시 승인으로 해석 |
| 거래 실행 어댑터(미구현) | 주문/체결 기록 | 아니오 | 승인된 한도·금액을 초과하는 주문 |
| 평가·회고 Skill | 평가·교훈·정책 개정 제안 | 아니오 | 성과가 좋았다는 이유로 정책을 자동 변경 |

**정책 예외:** 미래에 예외 절차가 필요하다면 승인자, 유효기간, 위반 항목, 사유를 별도로 기록해야 하며 기본값은 **예외 불허**다.

## 3. 최소 데이터 계약 v0 (개념 스키마)

이 절은 구현을 위한 **필드 수준 초안**이다. Python 클래스나 JSON Schema 파일을 이미 구현한 것으로 간주하지 않는다.

### 공통 Envelope

```json
{
  "schema_version": "0.1",
  "record_id": "uuid",
  "created_at": "2026-10-28T00:00:00+09:00",
  "as_of": "2026-10-27",
  "policy_id": "policy-default",
  "policy_version": "draft-1",
  "skill_name": "investment-team",
  "skill_version": "git-commit-sha",
  "model_id": "provider/model",
  "evidence_refs": [
    {"source": "DART", "document_id": "example", "published_at": "2026-10-27", "retrieved_at": "2026-10-28"}
  ]
}
```

- `created_at`: **생성 시간**; `as_of`: **판단에 허용된 정보의 마지막 시점**; `published_at`: 증거가 공개된 시간. 서로 대체하지 않는다.
- `policy_version`, `skill_version`: 사후 재현을 위한 식별자. 미확정 정책이면 승인 게이트는 차단한다.
- 인용 문서/기사의 `published_at > as_of`이면 그 증거를 해당 과거 시점 판단에 사용할 수 없다.
- 예시 필드 값은 실제 기업 분석 데이터가 아니다.

### InvestmentPolicy (Plan, 정책 소유자 승인 필수)

| 필드 | 의미 |
| --- | --- |
| `policy_id`, `version`, `status` | 정책 식별·불변 버전·draft/active/superseded |
| `owner`, `approved_by`, `approved_at` | 변경과 승인 추적 |
| `base_currency`, `investment_horizon` | 기준 통화·투자기간 |
| `objective`, `benchmark` | 투자 목적·성과 기준(없을 경우 명시적 null) |
| `eligible_assets`, `prohibited_assets` | 허용/금지 자산군과 시장 |
| `strategic_targets` | 자산군별 장기 목표 비중(합계 100% 검증) |
| `allocation_bands` | SAA 목표로부터 허용되는 편차 |
| `risk_limits` | 종목/섹터/국가/통화 집중도, 레버리지, 유동성 등 검증 가능한 한도 |
| `rebalance_policy` | 주기, 밴드 이탈 시 조치, 예외 |
| `approval_rules` | 승인 필요 행위, 금액/위험 상한, 만료 |
| `change_reason`, `supersedes` | 개정 근거 및 선행 버전 |

**미결정**: 구체적인 비중 숫자, 위험한도, 벤치마크, 투자 가능 자산군. Phase 1에서 사용자 결정 전에는 임의 초기값을 ‘승인된 정책’으로 배포하지 않는다.

### ResearchOpinion (Do, 기업 의견)

```json
{
  "ticker": "EXAMPLE",
  "market": "US",
  "rating": "buy",
  "confidence": "medium",
  "valuation": {"bear": null, "base": null, "bull": null, "currency": "USD"},
  "thesis": "가상의 투자 논지",
  "counter_thesis": "가상의 반대 논지",
  "invalidation_triggers": ["가상의 반증 조건"],
  "data_quality": "B",
  "source_report": "reports/example.md"
}
```

- `rating`은 기존 `매수/관망/회피`의 의미상 매핑값: `buy/watch/avoid`이며 **주문 명령이 아니다**.
- 투자 판단 점수와 확신도는 구분한다. 정성적 확신도를 임의 확률로 환산하지 않는다.
- 가설, 반대 가설, 반증 조건이 비어 있으면 심의 대상으로 올리지 않거나 `needs_research` 처리한다.

### PortfolioContext + PortfolioProposal (Do, 비중 제안)

`PortfolioContext`에는 `portfolio_id`, `positions`, `cash`, `prices_as_of`, `net_asset_value`, `base_currency`, `policy_version`을 포함한다.

`PortfolioProposal`에는 다음을 포함한다.

| 필드 | 의미 |
| --- | --- |
| `proposal_id`, `research_record_ids` | 근거 리서치와 연결 |
| `action` | add/increase/hold/reduce/exit |
| `current_weight`, `proposed_weight` | 현재·제안 비중 |
| `weight_basis` | **total_portfolio / equity_sleeve / theme_sleeve** |
| `portfolio_snapshot_id` | 판단 기준 잔고/환율/가격 스냅샷 |
| `impact` | 종목·섹터·국가·통화 집중도 및 예상 거래비용 영향 |
| `policy_checks` | 코드로 계산한 정책 규칙별 pass/fail/unknown |
| `rationale`, `alternatives` | 왜 이 규모인지·대안은 무엇인지 |
| `status` | draft / validation_failed / ready_for_review / submitted / rejected |

**우선순위:** 전체 포트폴리오 기준 정책 한도 > 자산군 한도 > 테마 한도 > 종목 리서치의 실행안 휴리스틱. 이 관계는 숫자가 아니라 **제약의 적용 우선순위**이다.

기존 `position_plan.py`의 기본 10%는 리서치 실행안의 **초안 휴리스틱**이다. 정책상 허용 비중으로 간주하지 않는다. `portfolio-review`의 집중도/현금 권장 범위도 동일하다.

### ApprovalDecision + ExecutionRecord (Do, 승인/체결)

`ApprovalDecision`: `proposal_id`, `policy_version`, `portfolio_snapshot_id`, `decision: approved|rejected|changes_requested`, `approved_by`, `approved_at`, `approval_scope`, `expires_at`, `reason`.

- **승인 불가**: 정책 `draft`/미확정, `policy_checks`에 fail 또는 unknown, 만료된 가격·잔고 스냅샷, 승인자 누락.
- **승인과 주문 분리**: `approved`여도 주문이 실제로 체결된 것은 아니다.
- `ExecutionRecord`는 미래에 `approval_id`, `order_id`, `filled_quantity`, `filled_price`, `fees`, `executed_at`, `status`를 담는다. 지금은 스키마 개념만 정의한다.

## 4. 유효성 검사·상태 전이 규칙

```text
ResearchOpinion → PortfolioProposal(draft)
    → validate:
         [fail/unknown] → validation_failed / needs_information
         [all pass]     → ready_for_review
    → 사용자에게 제출(submitted)
    → 사용자 승인(approved) 또는 거절(rejected)/수정요청
    → (미래) 주문 → 체결확인 → 실제 포트폴리오 반영
```

1. 모든 비중은 **분모**를 기록하고, 합계·환율·기준일을 확인한다.
2. 한도를 계산할 데이터가 없으면 `unknown`이며 `pass`로 변환하지 않는다.
3. 정책 위반을 LLM의 자신감/별점으로 덮지 않는다.
4. 승인 이후 정책·제안·포트폴리오 스냅샷이 변경되면 재검증해야 한다.
5. 주문체결의 부분체결·거절·취소는 독립 상태로 관리한다(구현 시 상세화).
6. Risk Validator는 최초 구현에서 필수 규칙만 결정론적으로 검증하고, 정성적 시나리오 검토는 의견으로 별도 보관한다.

## 5. 기존 Skill 및 도구와 호환하는 방법

| 기존 자산 | 유지할 것 | 연결/변경 방향(후속 Phase) |
| --- | --- | --- |
| `investment-research`, `investment-team` | 매수/관망/회피 라벨, 심층 논지, 4관점/교차반론 | 최종 보고서로부터 `ResearchOpinion` 어댑트; **자동 승인하지 않음** |
| `investment-checklist`, `quality-screen`, `industry-funnel` | 후보 발굴·빠른 거름망 | 후보와 탈락 사유를 연구 입력으로 연결 |
| `position_plan.py` | 비중·분할매수 **계획 기준선** | 투자정책/현재 자산 정보를 통과한 뒤에만 제안 후보로 사용 |
| `portfolio-review` | 보유 종목·상관관계·스트레스 테스트 | 승인된 투자정책을 입력해 자산배분·제안의 한도 위반 표기 |
| `decision-ledger` | 연구 판단의 사후 알파 평가, 교훈 기록 | **아이디어 성과 기록**으로 유지; 실제 보유 성과와 혼합 금지 |
| `thesis-tracker`, `news-pulse` | 반증 조건·이벤트 모니터링 | 제안된 행동이 자동 체결되지 않도록 승인 경계 유지 |
| `fact_sheet.py`, `report_check.py`, `report_audit.py` | 숫자 스냅샷·형식 검사·표본 검사 | 새로운 계약/정책 검사와 나란히 운용; 기존 검사 삭제 금지 |
| `run_state.py` | 단계별 완료 검증, 입력 고정·재개 | 정책/포트폴리오 버전도 재개 조건에 반영 |
| `dart_data.py`, `sec_edgar_data.py`, `fred_data.py` 등 | 기존 시점 제어·데이터 소스 계층 | `as_of`, 출처별 공시/조회시각 메타데이터로 정규화 |

**호환 정책:** 기존 `**판단**: 매수|관망|회피`, `**실행 계획**`, `## 실행 정보` 등은 `decision_ledger.py`·`report_check.py`가 읽는다. Phase 1에서 해당 라벨을 임의 변경하지 않고, 도메인 기록은 별도 JSON/DB 또는 어댑터로 추가한다.

## 6. 구현 순서와 수용 테스트 설계

| 단계 | 범위 | 완료 조건 |
| --- | --- | --- |
| Phase 0-2 | 책임·권한 및 개념 스키마 | 사용자 리뷰 가능한 설계 문서 + 호환 계획 |
| Phase 0-3 | 계약 검증 방식 구체화 | JSON Schema/타입, 상태 전이 단위 테스트 초안 |
| Phase 1 | 투자정책 정의 및 승인·버전 | 미승인 정책으로 실행안 승인이 불가능함을 테스트 |
| Phase 2 | SAA/TAA 배분 모형·기준 | 합계 100%, 밴드·분모·환율/시점 테스트 |
| Phase 3 | Research → Proposal → Approval 연결 | 매수 의견만으로 실제 거래가 발생하지 않음 |
| Phase 4 | 포트폴리오 위험·성과 분리 | 아이디어 평가와 실제 운용 평가 결과를 별도 산출 |
| 후속 | 실제 주문 시스템 | 명시적 사용자 승인, 주문·체결 전후 검증, 감사 로그 |

### 최소 수용 사례

1. 연구 결과가 `buy`여도 승인 기록이 없으면 주문은 **불가**.
2. 종목 연구의 10% 제안이 정책의 5% 한도를 초과하면 **거부**.
3. `weight_basis` 누락 시 합산·비교하지 않고 **거부**.
4. 정책이 `draft`이거나 `policy_checks`가 `unknown`이면 **승인 불가**.
5. 입력 정보가 `as_of` 이후 공개되었다면 **과거 판단 근거로 사용 불가**.
6. 투자 판단 원장의 매수 신호가 실제 체결 기록으로 계산되지 않아야 한다.
7. 기존 보고서 파서/검증 스크립트에 대한 회귀 테스트가 통과해야 한다.
8. 로컬/클라우드 모델 출력은 계약 검증과 정책 검증을 **동일하게** 통과해야 한다.

## 7. 사용자 확인 전 확정하지 않을 정책 변수

- 운용 계좌·포트폴리오 범위(단일 포트폴리오/다계좌), 기준통화
- 투자기간과 목적, 목표수익률과 벤치마크
- 허용 시장·자산군, 레버리지/공매도/파생상품 허용 여부
- SAA 목표/편차, 최대 종목·산업·국가 비중, 현금 최소/최대
- 손실 허용도·위험 예산·리밸런싱 주기
- 투자 승인 주체 및 주문 연계 범위

**권고:** Phase 1은 투자정책 템플릿의 필수 항목 정의와 승인 프로세스부터 시작한다. 구체적인 위험/수익 수치를 임의로 정하지 않는다.
