# Phase 1-3 — 투자정책(IPS) 작성·검토·승인·개정 절차

- 작성일: 2026-10-28
- 상태: **설계 초안**, 코드/Skill 구현 및 실제 정책 승인은 포함하지 않음
- 선행: [IPS 템플릿](investment-policy-template.md), [IPS 품질 평가 기준](ips-quality-criteria.md), [운용 아키텍처](architecture.md)
- 목적: 투자정책 초안에서 활성 정책, 개정 및 폐기까지 **권한·상태·기록·재검증**을 일관되게 정의한다.

## 1. 책임 경계

| 역할 | 책임 | 가능한 행위 | 불가능한 행위 |
| --- | --- | --- | --- |
| Policy Author Agent | 사용자 정보 수집, 충돌 탐지, 후보·대안 작성 | draft 작성·수정 제안 | 승인·활성화·소급 변경 |
| Quality Reviewer | 완전성/일관성 등 5차원 진단, 증거·검증 계획 | 품질 평가 보고서 | 최종 승인 |
| Policy Validator (결정론적 코드) | G01–G12 중 기계적으로 판단 가능한 규칙 검사 | pass/fail/unknown | 누락을 임의 가정으로 채우기 |
| Policy Owner (사용자) | 투자 목표·수치·제약 결정 | 명시적 승인·거절·개정·중지 | 정책 검사 결과를 마치 통과로 표시 |
| Policy Registry (코드) | 버전 저장·현재 정책 조회·감사로그 | 원자적 활성화·불변 이력 | 승인 없이 활성화 |

**권고:** 초기엔 단일 정책 소유자이되, 데이터 구조는 approval actor를 분리해 복수 역할로 확장 가능하게 한다.

## 2. 작성 인터뷰: 질문 순서와 결과

| 단계 | 질문 | 저장 필드 | 미응답 시 |
| --- | --- | --- | --- |
| A. 범위 | 연구용 모의 운용인가, 실계좌인가? 어떤 포트폴리오/계좌를 포함하나? | `portfolio_ids`, `policy_scope` | 초안 유지 |
| B. 목표 | 자산 증식/구매력 보전/현금흐름 목표와 우선순위는? | `objective`, `priorities` | 미정 표시 |
| C. 투자기간 | 최소 기간·중간 인출·자금 유입 계획은? | `horizon`, `cash_flow_needs` | 미정 표시 |
| D. 위험 | 손실 감수 **능력**과 **의향**은 각각? | `risk_capacity`, `risk_willingness` | 승인 차단 |
| E. 수익 | 목표수익의 필요조건/희망치 및 벤치마크는? | `required_return`, `desired_return`, `benchmark` | 승인 차단 또는 명시적 예외 심의 |
| F. 허용범위 | 허용/금지 자산, 레버리지·공매도·파생상품, 통화는? | `eligible_assets`, `prohibited_assets`, `base_currency` | 승인 차단 |
| G. 한도 | 종목/산업/국가/레버리지/현금 한도와 **분모**는? | `risk_limits` | 승인 차단 |
| H. 배분 | Phase 2 SAA 산출/승인 상태는? | `strategic_targets`, `allocation_bands` | full IPS 활성화 보류 |
| I. 운영 | 리밸런싱, 모니터링, 개정 주기와 승인자는? | `rebalance_policy`, `approval_rules` | 승인 차단 |

- 재정 상태 등 민감정보는 정책에 **최소한의 결정 기준만** 기록한다. 계좌번호·연락처·인증정보는 저장하지 않는다.
- 답변에 모순이 있거나 숫자가 없는 경우 **TBD + 누락 사유/담당자**를 명시하고 추정치로 채우지 않는다.
- 목적·제약에 따라 2~3개 정책 대안을 비교할 수 있지만 추천을 승인으로 간주하지 않는다.

## 3. 두 종류의 상태를 분리한다

**문서 작성 상태**와 **실제 효력 상태**를 한 필드에 섞지 않는다.

```text
작성: DRAFT -> QUALITY_REVIEW -> OWNER_REVIEW
         ^          |                 |
         |          v                 |
         +---- REVISION_REQUIRED <----+
                                      |
                                      v (명시적 승인 + 게이트 통과)
효력:                            ACTIVE
                                      |
                 +--------------------+-------------------+
                 v                                        v
             SUPERSEDED                              SUSPENDED
           (신버전 활성화)                      (소유자 중지/통제 사고)
                                                          |
                                            신규 승인·심사 후 ACTIVE 또는 RETIRED
```

- `DRAFT/QUALITY_REVIEW/OWNER_REVIEW/REVISION_REQUIRED`: 작성 워크플로 상태.
- `ACTIVE/SUSPENDED/SUPERSEDED/RETIRED`: 정책 효력 상태.
- 거절은 특정 **승인 요청**의 `REJECTED`이지, 모든 과거 정책의 삭제가 아니다.
- 정책 버전은 **불변**: 수정이 필요하면 새 draft revision을 만들고 승인 후 새 version을 발행한다.
- 동일한 `policy_id`와 적용 범위에 동일 시점 두 개의 ACTIVE 정책이 존재해서는 안 된다.
- 긴급 중지(SUSPENDED)는 신규 투자안 승인·주문을 차단한다. 기존 포지션의 정리 절차는 별도 승인된 안전 프로토콜로 정해야 하며 자동청산을 뜻하지 않는다.

## 4. 활성화 조건과 명시적 승인

활성화 전 검증 순서:

1. 필드 및 데이터 타입 확인.
2. G01–G12 hard gate 평가. 기계적 검사 불가인 G12(목표·위험·유동성의 실현 가능성)는 근거 있는 **사람의 검토**를 요구한다.
3. 5차원 품질 진단(0–3점)은 개선 가이드; 점수 15/15여도 게이트 위반 시 보류.
4. 정책 소유자에게 **적용 대상, 목표, 핵심 위험/배분 한도, 개정 diff, 효력 시작일**을 보여준다.
5. 명시적 사용자 승인 이벤트를 기록한다. 단순히 AI가 “승인됨”을 생성한 출력은 무효다.
6. 승인 시점에도 정책 버전·스냅샷이 불변인지 재검증하고 원자적으로 ACTIVE를 교체한다.

**정확성 원칙:** `unknown`인 필수 게이트는 `pass`가 아니다. 정책·수치가 미정인 상태는 리서치에 사용할 수 있지만 투자 제안 승인을 허용하지 않는다.

## 5. 정책 개정 프로세스

```text
변경 원인 감지/제안
 -> ChangeRequest(reason, evidence, requested_by)
 -> 기존 ACTIVE 정책 스냅샷 복제 -> 새 DRAFT 버전
 -> 차이(diff) + 위험/배분/기존 포지션 영향 평가
 -> 품질 검토 + G01–G12 + 사용자 심의
 -> APPROVE: 신규 ACTIVE 발행, 기존 ACTIVE는 SUPERSEDED
 -> REJECT: 기존 ACTIVE 유지, 개정안 REJECTED
```

**개정 유발 사건(예시)**: 투자 목적/기간/인출 계획 변경, 위험 감수 능력 변화, 자산군 전략 변경, 정책 위반 지속, 규제·세금 변화, 데이터/위험 측정 모델의 구조적 오류.

- 단순히 최근 수익률이 좋거나 나쁘다는 이유만으로 자동 개정하지 않는다.
- 개정이 위험 한도를 **완화**하는 경우 변경 전후 스트레스 시나리오 및 근거를 강조한다.
- `effective_at` 이전에 생성한 판단 기록은 당시 효력 정책에 고정한다.
- 신규 정책으로 기존 포지션이 위반되더라도 자동 매도하지 않고 **위반·조치 필요**로 기록한다.

## 6. 최소 감사 이벤트 계약

모든 이벤트에 `event_id`, `policy_id`, `policy_version`, `event_type`, `actor_type`, `actor_id`, `timestamp`, `previous_state`, `new_state`, `reason`, `document_hash`, `validation_run_id`를 기록한다.

이벤트 예시:

```json
{
  "event_id": "example-evt-1",
  "policy_id": "model-portfolio-1",
  "policy_version": "1.0-draft",
  "event_type": "POLICY_APPROVAL_REQUESTED",
  "actor_type": "user",
  "actor_id": "policy-owner",
  "timestamp": "2026-10-28T21:00:00+09:00",
  "previous_state": "OWNER_REVIEW",
  "new_state": "OWNER_REVIEW",
  "reason": "검토 요청",
  "document_hash": "sha256:example",
  "validation_run_id": "validation-example"
}
```

필요한 이벤트 유형: `DRAFT_CREATED`, `REVIEW_REQUESTED`, `VALIDATION_COMPLETED`, `REVISION_REQUESTED`, `POLICY_APPROVAL_REQUESTED`, `POLICY_APPROVED`, `POLICY_REJECTED`, `POLICY_ACTIVATED`, `POLICY_SUPERSEDED`, `POLICY_SUSPENDED`, `POLICY_RETIRED`.

**보관 원칙:** append-only 기록, 정책 내용 해시, 구버전 불변 보관, 승인 당시 검증 리포트 첨부. 개인정보·API 키는 이벤트에 기록하지 않는다.

## 7. 실패·예외 처리

| 상황 | 기대 동작 |
| --- | --- |
| 정책 수치 TBD | DRAFT 유지, 승인 거부 |
| G01–G12 hard gate fail/unknown | OWNER_REVIEW로 넘어가지 않고 보완 요청 |
| 평가자가 위험 완화 추천 | 제안으로만 기록, 원래 정책 유지 |
| 두 정책이 동시에 활성화 시도 | 범위/버전 충돌로 원자적 커밋 하나만 허용 |
| 승인 후 내용 변조 | 해시 불일치로 활성화 중단 |
| 승인자 권한 불일치 | 승인 거부 + 감사 이벤트 |
| 활성 정책 중지 | 새 투자 승인 차단, 기존 포지션 자동청산 금지 |
| 정성적 실현 가능성 미검증 | G12 UNKNOWN, 사람 검토 요청 |
| 기존 portfolio/position 데이터 없음 | 투자 제안/승인 차단, 자료 재수집 |
| 기존 투자원장의 매수 기록만 있음 | 체결 기록이나 사용자 승인으로 간주하지 않음 |

## 8. 기존 Skill·Tool과의 연결 및 호환

- `investment-research` 및 `investment-team`은 **리서치 판단**을 계속 생성한다. 투자정책 자체를 승인하지 않는다.
- `portfolio-review`는 ACTIVE 정책의 목표·한도와 현 보유를 비교하여 수정 제안을 낸다.
- `position_plan.py`의 기본 비중/분할매수 계산은 참고 휴리스틱이며, **정책에 의한 한도 검증**을 대체하지 않는다.
- `decision-ledger`는 **연구 판단 성과**를 저장한다. 정책 승인 원장과 혼합하지 않는다.
- `report_check.py`, `fact_sheet.py`, `run_state.py`의 기존 보고서 검사 및 스냅샷은 유지한다.
- 신규 Skill이 생겨도 기존 `**판단**`, `**실행 계획**`, `## 실행 정보` 파서와 파일명은 이 단계에서 변경하지 않는다.

## 9. 검증 계획 (향후 자동화할 수용 테스트)

| ID | 조건 | 기대 결과 |
| --- | --- | --- |
| L01 | DRAFT 정책에 대해 투자 승인 시도 | 차단 |
| L02 | 승인자 없는 정책 활성화 | 차단 |
| L03 | G06 자산배분 합계 미충족 | 차단 |
| L04 | 승인 직후 정책 본문 변경 | 해시 불일치로 차단 |
| L05 | 두 정책을 동일 범위에 동시 활성화 | 하나만 성공, 충돌 오류 |
| L06 | 기존 ACTIVE에서 새 DRAFT를 거절 | 기존 ACTIVE 유지 |
| L07 | 새 ACTIVE 발행 | 구버전 SUPERSEDED, 과거 기록 불변 |
| L08 | SUSPENDED 정책을 참조한 신규 제안 | 승인 차단 |
| L09 | 변경된 위험 한도의 기존 포지션 위반 | 자동 청산 없이 위반 보고 |
| L10 | LLM 응답이 “승인 완료”라고 주장 | 승인 이벤트 없으면 무효 |
| L11 | G12 정성 심사가 누락됨 | 활성화 차단 |
| L12 | 기존 보고서 라벨/판단 원장 | 기존 포맷 호환 유지 |

**현재 상태**: 이 표는 테스트 계획이지 테스트 실행 결과가 아니다.

## 10. Phase 1-4/1-5 인계

1. `.claude/skills/investment-policy/SKILL.md`: 정책 작성 인터뷰, 완전성·일관성 설명, 승인 요청까지(승인 권한 없음).
2. `tools/policy_validator.py` 및 스키마: 기계적 게이트와 상태 전이를 구현.
3. `tools/policy_registry.py`: 정책 버전/해시/이벤트 보관, 승인 기록; 처음엔 로컬 파일 기반이어도 됨.
4. `tools/tests`: L01–L12와 Phase 1-2 Q01–Q10 테스트.
5. 실제 정책 초안은 사용자 목표/제약을 수집한 뒤 생성. 그전에는 승인된 정책이 없는 것이 정상.

**중요:** 투자정책 **작성 지원**은 AI가 수행할 수 있지만, 실제 승인 기록 생성은 사용자 명시 행위에만 의존해야 한다.
