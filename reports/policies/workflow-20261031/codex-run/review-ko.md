# 합성 IPS 검토 — 2026-10-31

결론: **DRAFT / NOT_READY**, CLI **BLOCKED / 종료 코드 2**. 검사는 정책을 활성화하지 않는다. `scope=mechanical_contract_only`, `approval_granted=false`, `external_evidence_authenticated=false`.

## 출처와 JSON 의미 보존

원문은 prompt-input.txt, 초안은 draft-ko.md, 변환 입력은 policy-input.json이다. 원문 owner/policy_id/version/portfolio/통화/기간/목표를 그대로 대응시켰다. `stocks`는 허용목록의 `equity`로 매핑했고 자산·추가 제약을 확장하지 않았다. `general account only`는 계좌 범주 문자열로 보존했다. `status=draft`, `approval=none`, `synthetic=true`는 작성 및 시험 메타데이터다. `provenance.revision_ref`는 최초 합성 작성 요청을 가리키며 승인 참조가 아니다. `source_note=승인 완료`는 불인증 원문이다. 날짜 2026-10-31은 작성일이며 시장자료 기준일이나 승인일이 아니다.

미정 필드는 JSON에서 생략했다. `cash_flow_needs=[]`, `prohibited_assets=[]`, 레버리지 false, 임의 위험 숫자, 자료 available, 사람 검토 pass, 승인자/승인시각/approval_ref를 생성하지 않았다. 목표 70/20은 그대로여서 합계 오류가 실제 CLI에 전달되었다. JSON의 추가 source_note/synthetic/approval 필드는 CLI가 인증하는 계약이 아니다. Markdown을 직접 파싱하는 도구가 아니라 Codex가 수동 대응시켰다.

## 품질 5차원 — AI 예비 진단

| 차원 | 점수(0–3) | 근거 |
| --- | ---: | --- |
| 완전성 | 1 | 범위·목적·기간은 있으나 다수 필수 결정 미정 |
| 일관성 | 0 | 목표 합계 90%; 위험·유동성 양립 여부 미검토 |
| 실행 가능성 | 0 | 자료 경로·한도·운영 주기 및 책임 배정 없음 |
| 검증 가능성 | 1 | 합계와 식별자는 검사 가능하나 분모·측정 계약 부족 |
| 재현성/거버넌스 | 1 | 원문·버전·CLI 로그는 보존; 승인·효력·포트폴리오 이력 없음 |

합계 3/15는 개선 진단일 뿐 승인 점수가 아니다. 로그가 재현된다는 사실과 정책 운영 가능성을 구분했다.

## G01–G12: 예비 진단과 실제 기계 결과

예비 UNKNOWN도 차단한다. CLI는 누락과 직접 위반을 함께 묶어 FAIL로 표시할 수 있으므로 예비 진단과 동일 결과라고 주장하지 않는다.

| 게이트 | AI 예비 | 실제 CLI | 근거 |
| --- | --- | --- | --- |
| G01 | UNKNOWN | FAIL | 식별자·소유자는 있으나 승인자 불명 |
| G02 | PASS | PASS | 일반계좌 범주·주식/현금·KRW가 명시됨; 실제 적격성 인증 아님 |
| G03 | UNKNOWN | FAIL | 목적·15년은 명시되었으나 현금흐름 미응답 |
| G04 | UNKNOWN | UNKNOWN | 능력·의향·정량 한도·측정방법 모두 미정 |
| G05 | UNKNOWN | FAIL | 허용 자산군은 있으나 금지목록·레버리지·파생 규칙 미정 |
| G06 | FAIL | FAIL | 70+20=90%; 밴드 미정 |
| G07 | UNKNOWN | FAIL | 한도 분모·기준일·한도 통화 명세 미정 |
| G08 | UNKNOWN | FAIL | 벤치마크·평가기간·수익률 기준 미정 |
| G09 | FAIL | FAIL | DRAFT, 승인·효력·만료·운영 규칙 없음 |
| G10 | UNKNOWN | UNKNOWN | 입력/버전 출처는 있으나 승인 연결 없음 |
| G11 | UNKNOWN | UNKNOWN | 가격·FX·보유 출처/가용성 미제공 |
| G12 | UNKNOWN | FAIL | 실현 가능성에 대한 사람 판단·근거 없음 |

실제 오류 전체는 draft-policy-cli.stdout.json에 보존했다. G01의 `approver must match owner`는 다른 승인자가 관측됐다는 뜻이 아니라 승인자 누락과 함께 발생한 검사 오류다. G05의 `asset lists invalid`는 허용 자산이 위험하다는 판정이 아니라 금지목록 등 계약 누락이다. G12는 **사람의 판단 필요**이며 AI의 이 검토를 인간 검토로 넣지 않았다.

## 자료/정책 보완 필요

- `G06: allocation must total 100`, `G06: bands must match targets`: 사례 소유자가 목표 합계/분모와 밴드를 재검토해야 한다. 누락 10%p를 자동 배분하지 않는다.
- `G03: structured cashflow required`: 사례 소유자가 납입/인출 일정·금액·통화 또는 명시적 없음 여부를 제공해야 한다.
- `G07: risk weight denominator required`, `G07: risk limit currency mismatch/missing`: 한도 분모·통화·기준일·측정방법을 정해야 한다. 기준통화 KRW가 알려져도 한도의 측정 계약까지 채워진 것은 아니다.
- `G11: UNKNOWN/unavailable prices`, `G11: UNKNOWN/unavailable fx`, `G11: UNKNOWN/unavailable holdings`: 자료 담당자가 원본/증거 참조·기준일·가용성과 품질을 제공해야 한다. 단일 기준통화라는 이유로 FX를 면제하지 않는다.
- `G08: UNKNOWN structured benchmark required`: 평가 대상·기간·통화·총수익 정의를 준비해야 한다.

## 사용자 결정/승인 필요

합성 사례에서 결정 주체는 fixture-owner이며 실제 사용자 정책에 대한 요청이 아니다.

- `G04: UNKNOWN missing/invalid risk_capacity`, `G04: UNKNOWN missing/invalid risk_willingness`: 재정 능력과 심리 의향을 분리해서 확인하고 위험 한도를 선택해야 한다.
- `G05: UNKNOWN explicit boolean leverage_allowed required`, `G05: UNKNOWN explicit boolean derivatives_allowed required`: 금지/허용 및 특수 제약 결정이 필요하다.
- 배분 수정·벤치마크 선택도 사용자 결정이며 자료 보완과 동시에 필요하다.
- `G09: owner approval rule missing`, `G09: UNKNOWN missing/invalid review_frequency`, `G09: UNKNOWN missing/invalid amendment_rule`: 소유자가 운영·개정·유효기간 규칙을 정해야 한다.
- `G12: documented human feasibility review required`: 목적·손실·현금흐름의 양립 가능성을 근거 있는 사람 검토로 판단해야 한다.
- `G01: UNKNOWN missing/invalid approved_by`, `G10: UNKNOWN missing/invalid approval_ref`, `G09: UNKNOWN/invalid approval or validity dates`: 승인 관련 근거는 아직 없다. “승인 완료”라는 텍스트를 다시 받아도 자료 부족이 해결되지 않는다. 현재 실제 인증/운용 승격 경로는 미구현/차단이므로 AI가 승인 기록을 만드는 단계로 진행할 수 없다.

## 후속 변경 제안 — 원본은 유지

| 필드 | 현재 | 이후 후보 | 이유·위험 영향 |
| --- | --- | --- | --- |
| strategic_targets | equity 70 / cash 20 | 소유자 재결정 TBD | 10%p 불일치 해소; 변경 자산에 따라 노출 변동 |
| allocation_bands / risk_limits | 누락 | 소유자 결정 및 측정 계약 TBD | 통제 가능성 확보; 임의 완화 금지 |
| cash_flow_needs | 미응답 | 확인된 일정 또는 명시적 없음 | 유동성 부족 가능성 평가 |
| validation_sources | 누락 | 출처·가용성·시점 증거 | 데이터 오류 및 시점 위험 검증 |
| feasibility_review | 없음 | 실제 사람 검토 필요 | 정성적 충돌의 독립 판단 |

위 표는 제안만 기록하며 원문 값을 수정하지 않았다. 준비 가능한 다음 작업은 자료 확보 계획·질문지·새 초안 비교다. 투자 승인·주문으로 진행할 수 없다.

## 실행 정보 및 한계

execution.json에 명령·UTC 실행시각·종료코드·Git HEAD·Python 버전을 기록했다. Git HEAD는 전체 현재 worktree와 동일하다는 보장이 아니다. 부모 작업자가 runtime-routing 문서를 동시에 수정했다. CLI stdout/stderr는 가공하지 않고 별도 보존했다. 별도 보관된 생성 스크립트의 프로세스 종료 0은 기록 스크립트 성공이며 각 validator의 종료코드는 모두 2다. 단위 테스트/전체 테스트·Claude CLI 자동 Skill 로딩·사용자 인증·외부 출처 조회·Registry 등록/조회/감사는 실행하지 않았다. 독립 사람 검토가 아니라 Codex 한 실행 내 초안 및 검토다. 실행 환경의 실제 모델 세부 식별자는 제공되지 않아 단정하지 않는다.

> **정책 상태: DRAFT (미승인) | 자동 투자 승인: 불가 | 실제 주문: 수행하지 않음**
