# 정책 Skill 연동 검증 중간 보고서

## 결론

#52의 CLI 계약 검증을 수행했다. 실제 Claude Skill 런타임은 미실행이며 이슈는 미결로 유지한다.

- canonical Skill의 “도구 미구현” 설명을 현재 Validator/연구용 Registry 계약에 맞게 수정했다.
- Markdown→JSON은 수동 검토 단계, PASS는 기계적 검사, 연구용 등록은 실제 ACTIVE가 아님을 명시했다.
- 자료/정책 보완 필요와 사용자 결정/승인 필요의 출력 항목을 구분했다. 자연어 출력 준수는 실제 런타임 검증 대상으로 남긴다.
- 신규 9개 subprocess CLI 통합 테스트와 기존 테스트를 실행했다: **219 tests / OK / 0.687초 / ResourceWarning 0건**.
- 전체 명령: `python3 -W always::ResourceWarning -m unittest discover -s tools/tests -v`.
- Work의 `command -v claude`에서 실행 파일을 찾지 못했다. Claude 실행 성공이나 인증 여부를 주장하지 않는다.

## 시나리오와 남은 작업

[연동 검증 계약](../../../methodology/fund-management/policy-workflow-validation.md)에 입출력, CLI 사례 9종, 실제 런타임 후속 절차를 기록했다. DRAFT·승인 누락·버전/snapshot 불일치 차단, 합성 연구 등록→조회→제안 차단을 확인했다. 실제 인터뷰·문서 의미 보존·Skill 자동 로딩·자연어 출력 검증은 남았다.

기존 실제 IPS, 보고서 라벨, 원장, 시장 데이터와 백테스트 엔진은 변경하지 않았다. 백테스트 재실행 대상이 아니다. 실제 정책 활성화·주문 실행 없음.

## 실행 정보

- 작성일: 2026-10-31 KST.
- 환경: ChatGPT Work Linux, Python subprocess, 임시 디렉터리.
- 선행 main: `875a9363ab2f2d0d8ef33670481f7571439c4a36`.
- 자료: 저장소 코드와 합성 테스트 fixture. 실제 시장 데이터 사용 없음.
- Skill: canonical investment-policy 문서 수정·계약 점검. 실제 Claude Skill 실행은 하지 않음.
- 수정 방법: skill-creator의 기존 지침 수정 원칙 참고. 개인 Skill 설치/변경이 아니라 사용자 지정 GitHub 저장소의 프로젝트 Skill 수정이며 해당 PR로 보존한다.
