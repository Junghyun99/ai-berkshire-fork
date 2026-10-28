# Phase 0-3 — 운용 데이터 계약·검증 규칙·상태 전이 설계

- 작성일: 2026-10-28
- 상태: 설계 및 샘플 계약 정의. **실거래·기존 Skill 수정 없음**.
- 상위 문서: [architecture.md](architecture.md) (Phase 0-2).
- 목적: 클라우드/로컬 LLM에 공통 적용할 입력·출력 계약, 승인 통제, 검증 시나리오를 확정할 수 있도록 만든다.

## 1. 데이터 흐름과 신뢰 경계

```text
Skill → ResearchOpinion → PortfolioProposal → deterministic PolicyValidator
                                                 ├─ invalid/unknown → BLOCKED
                                                 └─ pass → READY_FOR_REVIEW
                                                               ↓
                                               explicit human approval
                                                               ↓
                                             APPROVED (not an order)
                                                               ↓
                                             Execution adapter (future)
```

LLM이 생성한 JSON은 **검증 전에는 신뢰하지 않는다**. 스키마 적합성은 충분조건이 아니다. 정책/가격/증거/잔고 확인을 추가로 수행한다.

## 2. 계약 버전과 식별자

- 모든 기록에는 `schema_version`(현재 `0.1.0`), `record_id`, `created_at`, `as_of`, `policy_id`, `policy_version`, `skill_name`, `skill_version`, `model_id`, `evidence_refs`를 포함한다.
- `record_id`, `proposal_id`는 재사용 금지. 동일 내용의 재실행은 새 ID 또는 명시적 idempotency key로 구분한다.
- `created_at`은 타임존 포함 ISO-8601, `as_of`는 YYYY-MM-DD.
- `published_at`이 `as_of`보다 늦으면 해당 증거는 과거 판단에 사용할 수 없다.
- 투자 제안은 분석 결과의 `record_id`를 참조하고, 승인은 제안의 `proposal_id`와 정책·포트폴리오 스냅샷을 고정한다.
- `0.1.x`: 필수 필드를 제거하지 않는 호환 확장, `0.2.0` 이상: 변경 시 마이그레이션/어댑터 검토. 이는 **제안하는 버전 규칙**이다.

## 3. 최소 개념 계약

### 3.1 InvestmentPolicy

필수 필드:
- `policy_id`, `version`, `status: draft|active|superseded`
- `owner`, `approved_by`, `approved_at` (draft는 승인 값 null 가능)
- `base_currency`, `investment_horizon`, `objective`, `benchmark`
- `eligible_assets`, `prohibited_assets`, `strategic_targets`, `allocation_bands`, `risk_limits`, `rebalance_policy`, `approval_rules`

정책이 활성화될 때: `approved_by`/`approved_at` 필수; `strategic_targets`의 비중 총합 100%; 각 밴드의 하한 ≤ 목표 ≤ 상한; 서로 충돌하는 금지/허용 자산은 오류. 이들은 **JSON 문법 검사 외의 의미 검증**이다. 사용자가 아직 수치를 확정하지 않았다면 `draft`만 허용한다.

### 3.2 ResearchOpinion

- `rating: buy|watch|avoid`: 기존 보고서 `매수|관망|회피`의 의미적 대응일 뿐 승인/주문 아님.
- `ticker`, `market`, `source_report`, `thesis`, `counter_thesis`, `invalidation_triggers`, `data_quality` 필수.
- `valuation`: `bear/base/bull/currency`를 명시, 산출 불가 시 null과 사유를 기록.
- 근거 부재/시점 위반은 `NEEDS_RESEARCH`로 격리. `confidence`를 정책 위반 면제에 사용하지 않는다.

### 3.3 PortfolioContext / PortfolioProposal

- PortfolioContext: `portfolio_id`, `snapshot_id`, `positions`, `cash`, `net_asset_value`, `base_currency`, `prices_as_of`, `policy_id`, `policy_version`.
- PortfolioProposal: `proposal_id`, `research_record_ids`, `portfolio_snapshot_id`, `action`, `current_weight`, `proposed_weight`, `weight_basis`, `policy_checks`, `rationale`, `status`.
- `weight_basis`: `total_portfolio|equity_sleeve|theme_sleeve`. 서로 다른 분모의 비중을 합산하지 않는다.
- `policy_checks`의 결과: `pass|fail|unknown`. 하나라도 `fail` 또는 `unknown`이면 승인 준비 상태가 될 수 없다.
- 정책상 한도와 `position_plan.py`의 휴리스틱 10% 상한이 충돌하면 **승인 정책**이 우선한다. 이 10%는 승인된 상한이 아니다.

### 3.4 ApprovalDecision / ExecutionRecord

- ApprovalDecision: `decision_id`, `proposal_id`, `decision: approved|rejected|changes_requested`, `approved_by`, `approved_at`, `policy_version`, `portfolio_snapshot_id`, `expires_at`, `reason`.
- 사용자 **명시 승인 이벤트** 이외에는 `approved` 생성 금지. LLM 결과 텍스트에서 승인 추론 금지.
- ExecutionRecord (미래 확장): `approval_id`, `order_id`, `filled_quantity`, `filled_price`, `fees`, `executed_at`, `status`. **이 PR은 주문 기능을 구현하지 않는다**.

## 4. 제안 상태기계

```text
DRAFT
  ├─ validate(error or unknown) ──> BLOCKED
  └─ validate(all pass) ──────────> READY_FOR_REVIEW
READY_FOR_REVIEW ─ submit ────────> SUBMITTED
SUBMITTED ├─ reject ──────────────> REJECTED
          ├─ request changes ─────> CHANGES_REQUESTED ─ revise ─> DRAFT (새 버전)
          └─ explicit approval ───> APPROVED
APPROVED ─ policy/portfolio/prices changed ─> REVALIDATION_REQUIRED
```

- `BLOCKED`의 원인을 해소하면 수정 버전으로 `DRAFT`부터 재검증한다.
- `APPROVED`는 투자 승인의 증거일 뿐, 체결 완료를 뜻하지 않는다.
- 이미 승인된 제안을 수정하여 재활용하지 않고 새 버전/새 제안으로 연결한다.
- **검증 불가, 정보 부족, 한도 초과는 fail-closed**.

## 5. 검사 계층

| 검사 계층 | 수행 주체 | 실패 시 |
| --- | --- | --- |
| JSON 구조/타입/열거형 | JSON Schema 검증기 | 입력 반려 |
| 시점/출처/스냅샷 일관성 | 결정론적 Evidence Validator | NEEDS_RESEARCH/BLOCKED |
| 정책 값 의미 검증 | InvestmentPolicy Validator | 정책 활성화 거부 |
| 포지션 한도·비중 분모·통화 정규화 | Portfolio Risk Validator | BLOCKED |
| 승인 주체·만료·정책 버전 | Approval Gate | 승인 거부 |
| 기존 출력·감사 도구 회귀 검증 | `report_check.py`, `decision_ledger.py`, 테스트 | 배포 중단 |

**임계값을 마법 숫자로 만들지 않는다.** 가격 스냅샷 만료 정책, 리밸런싱 밴드, 집중도 한도는 Phase 1에서 소유자가 지정한다.

## 6. 수용 시나리오 (구현 단계에서 자동화)

| ID | 입력/상황 | 기대 결과 |
| --- | --- | --- |
| C01 | 리서치가 `buy`이지만 승인 없음 | 주문/승인 자동 생성 금지 |
| C02 | 정책 종목 한도 5%, 계획 비중 10% | `BLOCKED` |
| C03 | `weight_basis` 누락 | 스키마 실패 |
| C04 | 정책 `draft` | `APPROVED` 전환 불가 |
| C05 | 정책 검사 중 `unknown` | `BLOCKED` |
| C06 | `published_at > as_of` | 과거 리서치 증거로 사용 불가 |
| C07 | 승인 이후 포트폴리오 스냅샷 변경 | `REVALIDATION_REQUIRED` |
| C08 | 다른 분모의 비중을 직접 더함 | 오류 또는 계산 금지 |
| C09 | 동일 제안에 사용자 승인 이벤트 없음 | 승인 거부 |
| C10 | `decision-ledger`의 매수 판단 | 실제 체결·보유로 계산 금지 |
| C11 | 기존 보고서 라벨/형식 유지 | 기존 `report_check.py`, `decision_ledger.py` 회귀 테스트 |
| C12 | 동일 입력의 로컬/클라우드 LLM | 동일 구조·정책 검증 규칙 적용 |
| C13 | 정책 목표 비중 합계 ≠ 100% | 정책 활성화 거부 |
| C14 | 승인 만료 이후 주문 시도 | 승인 무효 및 재검토 |

## 7. 실제 구현을 위한 권장 인터페이스

```python
class PolicyValidator:
    def validate_policy(self, policy) -> list: ...
    def validate_proposal(self, policy, portfolio, proposal) -> list: ...

class ApprovalGate:
    def submit(self, proposal_id, validated_snapshot_id): ...
    def decide(self, proposal_id, user_approval_event): ...

class ResearchAdapter:
    def from_existing_report(self, report_path) -> dict: ...
```

이 코드는 **인터페이스 예시**이며 저장소에 실행 가능한 모듈로 구현한 것은 아니다.

## 8. 구현을 시작할 때의 순서

1. 공통 Envelope, Policy, ResearchOpinion, Proposal, Approval 계약을 각각 JSON Schema 파일로 구체화한다.
2. 합계 100%, 정책 상태, 시점 검증, 리스크 검사, 승인 상태 전이는 Python 코드로 구현한다.
3. C01~C14에 해당하는 **오프라인 단위 테스트**를 작성한다.
4. 기존 출력 파서와 도구의 회귀 테스트를 실행한다.
5. Phase 1에서 사용자가 정한 정책 값을 버전과 함께 저장한다.
6. 실제 주문 연결은 별도 작업·명시적 승인 이후에만 진행한다.

## 9. 미해결 설계 질문

- 복수 계좌를 하나의 정책으로 관리할지, 계좌별 하위 정책을 둘지
- 기준통화/환율 스냅샷의 공식 출처와 업데이트 방식
- 시간 경과에 따른 승인·가격 스냅샷 유효기간
- 거래 비용·세금 및 현금 지급 의무의 모델 범위
- 벤치마크와 계좌 수익률 계산(TWR/MWR)의 기준
- 단계별 승인자를 실제 사용자 1명으로 고정할지 확장 가능 구조로 둘지

이 항목들은 **Phase 1의 정책 정의에서 결정**한다. 기본 숫자를 임의로 승인된 정책처럼 넣지 않는다.
