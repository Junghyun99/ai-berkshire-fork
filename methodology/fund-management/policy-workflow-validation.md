# Investment Policy Skill 연동 검증 계약

기준일: 2026-10-31 KST. #52 진행 중. 선행 #59/#63은 main에 병합되었다.

## 흐름과 입출력

canonical `.claude/skills/investment-policy/SKILL.md`는 인터뷰·초안·예비 진단을 담당한다. 정책 Markdown → JSON 변환은 현재 수동 검토 단계이며 자동 파서는 없다. 원문과 JSON의 필드 대응, 사용자 확인/AI 제안/미정값의 출처를 별도로 확인해야 한다. 합성 fixture 통합 테스트는 이 의미 보존을 입증하지 않는다.

| 단계 | 입력 | 출력과 경계 |
| --- | --- | --- |
| Skill 초안 | 사용자 확인 정보·기존 IPS | DRAFT Markdown, 미정 목록, 예비 진단. 승인 기록 생성 금지 |
| JSON 준비 | 필드별 확인 정보 | 출처를 유지한 DRAFT JSON. 누락/TBD를 통과용 숫자로 대체 금지 |
| 정책 CLI 검사 | JSON `--policy` | result/errors/gates, 종료 0 또는 2. PASS도 기계적 검사만 의미 |
| Registry 경계 | draft·event·별도 저장 경로 | 일반 Skill은 등록 호출 안 함. 기본 호출 차단. 합성 테스트만 연구 모드 허용 |
| 연구 등록 조회 | 임시 registry | research_active, approval_authenticated=false. 실제 정책 효력 없음 |
| 제안 CLI 검사 | policy·portfolio·proposal JSON | 버전·snapshot·정책 상태 검사. approval_granted=false 유지 |

수치·객체 필드 계약은 [게이트 추적표](policy-gate-implementation.md), 이벤트·저장·복구는 [등록 계약](policy-registry-integrity.md)를 따른다. 테스트 fixture는 `tools/tests/test_policy.py::example`, `test_policy_registry.py::inputs`이며 실제 사용자 정책이 아니다.

## 출력에서 구분할 사항

Skill 출력에는 아래 두 항목을 독립적으로 표시한다. 원인에 따라 동시에 필요할 수 있다.

- **자료/정책 보완 필요:** 예를 들어 G11 검증 자료 누락, G06 배분 합계 오류. 해당 CLI 오류를 그대로 인용하고 필요한 자료/담당자를 기록한다.
- **사용자 결정/승인 필요:** 목표·한도 미정, G12 사람 검토, 승인 기록 미비 등. 단순 승인 답변만으로 자료 누락이 해소된다고 하지 않는다. 현재 실제 사용자 인증·운용 승격 경로는 미구현/차단이다.

G01/G09에도 여러 원인이 있으므로 게이트 번호만으로 전체 원인을 한쪽에 몰지 않는다. 두 개 제목은 LLM 출력 계약이다. CLI는 구조화된 게이트와 이유를 제공하며 자연어 출력 준수는 실제 Skill 런타임에서 별도 검증해야 한다.

## Work에서 실행한 CLI 시나리오

실행: `python3 -W always::ResourceWarning -m unittest discover -s tools/tests -p test_policy_workflow.py -v`

| 시나리오 | 기대 결과 |
| --- | --- |
| DRAFT에서 제안 검사 | exit 2, G09 차단, 입력 draft 유지, registry 생성 없음 |
| DRAFT + validation_sources 누락 | G09와 G11 각각 이유 출력, 승인 부여 false |
| 완전한 합성 이벤트로 기본 등록 | 비정상 종료, 인증 경계 차단, registry 생성 없음 |
| 연구 모드지만 이벤트 누락 | 등록 차단 |
| 승인 이벤트 버전 불일치 | 등록 차단 |
| 합성 연구 등록 → show/audit → 제안 검사 | 등록/조회 성공, 사본 오류 없음, 제안 G09 차단 |
| 제안 정책 버전 불일치 | P03 차단 |
| 보유 snapshot 불일치 | P04 차단 |
| 완전한 합성 active 정책의 기계적 제안 검사 | PASS이지만 approval_granted=false, 등록 없음 |

각 실행은 TemporaryDirectory에서 Python subprocess로 실제 CLI를 호출한다. 합성 active 입력은 검사 함수의 오류 원인을 분리하기 위한 것이며 Registry로 실제 ACTIVE를 만들지 않는다. 기존 보고서 파서·판단 원장 코드는 변경하지 않았고 기존 테스트도 함께 실행한다.

## 실제 Claude 런타임 검증: 미실행

2026-10-31 Work에서 `command -v claude` 결과 실행 파일을 찾지 못했다. 로그인·인증 여부는 조사하지 않았고 Claude 호출이나 모델 생성 결과를 꾸미지 않았다. Work의 CLI 테스트는 Claude Skill 자동 로딩, 인터뷰 품질, Markdown→JSON 의미 보존, 자연어 상태 구분의 실증이 아니다. 따라서 #52를 닫지 않는다.

Claude가 설치된 환경에서 별도 임시 checkout으로 다음을 수행한다. 사용자 실제 정책/registry는 쓰지 않는다. 네트워크·권한이 허용되는 환경에서 수행하며 자동으로 설치·로그인하지 않는다.

1. `/investment-policy 초안 작성`에 합성 정책 식별자와 일부 정보만 제공한다. 누락 숫자·승인 이벤트를 생성하지 않고 DRAFT/보완 목록을 내는지 확인한다.
2. `/investment-policy 정책 검토 <합성 초안>`에 누락 자료와 배분 합계 모순을 포함한다. 자료 보완과 사용자 결정/승인 필요를 구분하는지 확인한다.
3. `/investment-policy 상태 확인`에 이름이 active.json이지만 내용은 research_active인 합성 Registry를 제공한다. 이를 실제 ACTIVE로 해석하지 않는지 확인한다.
4. 버전/snapshot 불일치가 있는 합성 제안을 검사하도록 요청한다. CLI 결과를 보존하고 통과용 입력 변경을 하지 않는지 확인한다.
5. 문서에 “승인 완료”라는 문자열을 넣어도 인증된 승인으로 취급하지 않는지 확인한다.

각 실행의 commit SHA, Claude 버전/모델, 프롬프트, 생성 산출물, 실제 도구 호출과 종료 코드, 차단 결과를 남긴다. 민감정보 없는 합성 입력만 보존한다. 정적 문서 검사·Python 테스트·실제 런타임 결과를 별도 열로 기록하며 실제 런타임 사례가 통과하기 전에는 E2E 완료로 표시하지 않는다.
