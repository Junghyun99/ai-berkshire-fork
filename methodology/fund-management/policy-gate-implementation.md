# G01~G12 정책 검증 구현 계약 — 2026-10-30

추적: #50. 설계 기준은 [품질 게이트](ips-quality-criteria.md), [수명주기](ips-lifecycle.md). 이 문서는 자동 검사와 외부 판단의 경계를 구체화한다. 실제 IPS v0.4를 채우거나 활성화하지 않는다.

## 의미와 호환성

`check_policy(policy, as_of=None)`는 기존처럼 오류 문자열 목록을 반환한다. `check_proposal`과 registry도 이 함수를 거쳐 미완성 정책을 차단한다. 기존 CLI의 `policy/proposal --policy` 호출, `result/errors`, 정상 0/차단 2 exit code를 유지한다.

새 `evaluate_policy`와 policy CLI는 G01~G12별 PASS/FAIL/UNKNOWN, `scope=mechanical_contract_only`, `approval_granted=false`, `external_evidence_authenticated=false`를 제공한다. **PASS는 아래 입력 계약에 대한 기계 검사 통과일 뿐 실제 승인·자료 진위·투자 가능성의 인증이 아니다.** 누락/미상은 오류 목록에 포함되어 기존 호출자에서도 차단된다. 여러 원인이 함께 있으면 FAIL로 집계될 수 있으며 UNKNOWN도 차단이라는 효과는 같다.

필수값이 부족해 예전에 통과하던 입력은 이제 차단된다. 필드를 임의 기본값으로 채우는 호환 모드는 제공하지 않는다. 기존 테스트의 정상 fixture만 명시적 합성 완성 계약으로 확장했으며 실제 정책 파일·Skill은 수정하지 않는다. 완전한 JSON Schema를 도입한 것이 아니라 아래 명시적 계약을 검사하는 stdlib 도구다.

## 설계-구현 추적표

| 게이트 | 이전 빈틈 | 이번 기계 검사 | 남은 외부 확인/범위 |
| --- | --- | --- | --- |
| G01 소유 | 일부 필드 존재만 검사 | owner/policy_id/approved_by 문자열, portfolio_ids, 단일 소유자와 승인자 일치 | 실제 신원 인증·승인 진위는 #51 |
| G02 범위 | 계좌 범위 미검사 | policy_scope.accounts 비어 있지 않은 고유 문자열 목록, 3자리 대문자 ASCII 통화 코드 형식 | 실제 계좌 적격성·ISO 통화 존재 확인·전체 보유 포괄성은 별도 |
| G03 목표 | 목적/기간 타입, 현금흐름 내용 미검사 | 비어 있지 않은 목적·기간, 명시적 현금흐름 이벤트 목록, 양수 금액·종류·날짜·기준통화 | 미래 납입 가능성·인출 필요·기간 해석은 사용자/Phase 2-4 |
| G04 위험 | 단일종목 한도 위주 | 능력/의향 각각 명시, 종목·섹터·유동성 % 한도 0~100, 총노출 배수 ≥1, 측정방법 | 해당 한도의 경제적 타당성·계좌별 규제·전체 위험 종류는 별도 |
| G05 자산 | 비정상 목록 예외, 레버리지 선언 누락 | 문자열 목록·중복·허용/금지 중첩, 레버리지/파생 허용 boolean, 레버리지 금지와 >1배 한도 모순 | 상품명에서 실제 경제적 노출·파생 여부를 추론하지 않음 |
| G06 배분 | 목표 자산 허용목록 연결 누락 | 합계 100, 밴드 일치/범위, 목표 자산이 허용목록에 포함 | 최적 배분·보유의 실제 합산·계좌 배치는 별도 |
| G07 기준 | 분모 외 통화·날짜 누락 | total_portfolio 분모, 한도 통화와 기준통화 일치, 기준일 형식·미래일 차단 | 실제 포트폴리오 평가·날짜 간 신선도 기준은 별도 |
| G08 벤치마크 | 단순 문자열 존재 | 이름·평가기간·수익률 기준·통화 또는 사유/소유자/근거가 있는 명시적 예외 | 벤치마크 적절성·예외 승인 진위는 사람 검토 |
| G09 운영 | 변경/검토/만료 누락 | owner_approval_required, 리밸런싱·검토 주기·개정 규칙, 날짜 순서·미래일·만료 규칙 | 문장 의미·주기 실행·초 단위 효력 전이·인증은 #51/후속 |
| G10 출처 | 버전 외 추적 미비 | 출처 목록·승인/개정 참조·policy_id/version 일치 | 참조 문서 실제 존재·해시·변조 검증은 #51 |
| G11 자료 | 소스 확보 계약 미구현 | prices/fx/holdings의 available 선언·근거 참조·기준일 | 실제 자료 조회·품질·가용성은 #53/#54; 선언만으로 인증하지 않음 |
| G12 실현 가능성 | reviewer/reason만 검사 | user 검토 기록·근거·정책 버전·검토일·미해결 충돌 빈 목록 | 실제 사람이 검토했는지와 정성적 타당성은 #51/#52 및 사용자 판단 |

테스트: `tools/tests/test_policy_gates.py`의 12개 게이트 누락 매핑, 불완전 자료 UNKNOWN, 승인으로 오인하지 않는 출력, 비정상 목록/중복, 허용 밖 배분, 레버리지 모순, 숫자 경계, 벤치마크 예외, 날짜/버전/검토 충돌, 현금흐름, malformed 입력, 비변경성, CLI 회귀를 확인한다. 이전 `test_policy.py`의 정책·제안·불변 archive 테스트를 유지한다.

## 추가 필드 계약 및 마이그레이션

숫자는 정책 소유자가 결정한 값 또는 **테스트용 합성 값**만 입력한다. 아래는 타입 설명이며 사용자 정책값의 추천이 아니다.

- `portfolio_ids`: 실제 계좌번호가 아닌 포트폴리오 별칭 문자열 목록.
- `policy_scope.accounts`: 적용 계좌 범주/별칭 목록. 허용 자산 범위는 기존 `eligible_assets`로 연결한다.
- `cash_flow_needs`: 이벤트 목록. 각 항목은 `type=contribution|withdrawal`, 양수 `amount`, 기준통화 `currency`, ISO `date`. `[]`는 명시적으로 예정 외부 흐름 없음이며 미응답과 구별한다. 종전 임의 dict 입력은 이 목록으로 명시적으로 전환해야 한다. 반복 현금흐름·외화 납입은 향후 계약 범위이며 조용히 추정하지 않는다.
- `risk_limits`: 기존 `single_name_max_pct`, `weight_basis`에 `sector_max_pct`, `liquidity_min_pct`, `gross_leverage_max`, `measurement_method`, `currency`, `as_of` 추가. 총노출 배수는 1이 100%다. 국가는 이번 필수 정량 한도에 포함하지 않았으며 추가 정책 한도를 전부 검증한다고 주장하지 않는다.
- `asset_rules`: `leverage_allowed`, `derivatives_allowed`는 실제 boolean. 문자열 `"false"`나 숫자 0/1로 대체하지 않는다. ETF 상품 분류 자체를 이 코드가 판정하지 않는다.
- `benchmark`: `name`, `currency`, `evaluation_period`, `return_basis` 문자열. 예외라면 `exception=true`, `reason`, `approved_by=owner`, `evidence_ref`를 제공한다. 이 참조는 인증된 전자서명이 아니다.
- `approval_rules`: 기존 owner 승인 필수 boolean에 `review_frequency`, `amendment_rule` 추가. `rebalance_policy.frequency`도 필수다.
- `expiry_rule`: `until_superseded`(expires_at 없음) 또는 `fixed_date`(expires_at 필수). 만료일 당일부터 차단한다. `approved_at <= effective_at <= 평가일`을 **UTC 날짜 단위**로 검사한다. timestamp는 시간대 필수, 날짜 문자열도 허용한다. 동일 UTC 일자 내 시각 순서를 완전히 검사하는 기능은 아니다. 기본 평가일은 현재 UTC 날짜이며 Python API의 `as_of`로 재현 기준일을 줄 수 있다.
- `provenance`: `policy_id`, `policy_version`, `sources` 목록, `approval_ref`, `revision_ref`. 최초 버전도 최초 작성 근거를 참조한다.
- `validation_sources`: `prices`, `fx`, `holdings` 각각 `status=available`, `evidence_ref`, `as_of`. 환율이 불필요한 단일통화 정책도 그 근거를 명시한 FX 자료 처리 계약을 제공해야 하며 자동 면제하지 않는다.
- `feasibility_review`: 기존 result/reviewer/reason에 `actor_type=user`, `policy_id`, `policy_version`, `reviewed_at`, `evidence_ref`, `unresolved_conflicts=[]` 추가. 검토일은 승인일보다 늦을 수 없다.

공백/TBD/UNKNOWN/TODO는 필수 문자열의 유효 값이 아니다. 계좌·원본·검토 참조가 실제로 존재하는지는 이번 로컬 구조 검사만으로 알 수 없다. 장래 #51의 신뢰 경계에서 증거를 인증해야 한다. G11/G12의 모든 정보를 AI가 작성했다는 이유만으로 실제 검증 완료로 처리해서는 안 된다.

## 변경하지 않은 경계

정책 ACTIVE 설정·승인 이벤트 생성·실제 계좌·주문·데이터 수집은 수행하지 않는다. proposal validator도 모든 보유/섹터/레버리지 위험을 새로 계산하는 엔진으로 바뀐 것은 아니다. 이번 보완은 **정책 계약의 누락·모순 차단**이며 #51 등록 안전성, #52 종단간 검사, Phase 2-4 운용 제약은 별도다.
