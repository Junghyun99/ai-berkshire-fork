# 정책 Skill Codex/Work 연동 검증 보고서

## 결론

#52의 CLI 계약 검증에 이어 사용자 승인 D-016에 따라 Codex/Work에서 canonical Skill을 명시적으로 읽는 실제 에이전트 실행을 수행했다. 해당 사례의 초안·검토·JSON·상태 해석과 CLI 결과를 확인했다. PR 검토·병합 전이므로 이슈는 아직 미결이며 Claude 자동 로딩/런타임은 별도 미검증이다.

- canonical Skill의 “도구 미구현” 설명을 현재 Validator/연구용 Registry 계약에 맞게 수정했다.
- Markdown→JSON은 수동 검토 단계, PASS는 기계적 검사, 연구용 등록은 실제 ACTIVE가 아님을 명시했다.
- 자료/정책 보완 필요와 사용자 결정/승인 필요의 출력 항목을 구분했다. 자연어 출력 준수는 실제 런타임 검증 대상으로 남긴다.
- 신규 9개 subprocess CLI 통합 테스트와 기존 테스트를 실행했다: **219 tests / OK / 0.705초 / ResourceWarning 0건** (Codex 실행 준비 중 재검증).
- 전체 명령: `python3 -W always::ResourceWarning -m unittest discover -s tools/tests -v`.
- Work의 `command -v claude`에서 실행 파일을 찾지 못했다. Claude 실행 성공이나 인증 여부를 주장하지 않는다.

## 시나리오와 남은 작업

[연동 검증 계약](../../../methodology/fund-management/policy-workflow-validation.md)에 입출력, CLI 사례 9종, 실제 런타임 후속 절차를 기록했다. DRAFT·승인 누락·버전/snapshot 불일치 차단, 합성 연구 등록→조회→제안 차단을 확인했다. 아래 합성 사례에서 문서→JSON 의미 보존과 자연어 상태 구분을 대조했다. 실제 사용자 인터뷰의 다회차 품질, 자동 Skill 로딩과 Claude 호환성은 별도 미검증이다.

기존 실제 IPS, 보고서 라벨, 원장, 시장 데이터와 백테스트 엔진은 변경하지 않았다. 백테스트 재실행 대상이 아니다. 실제 정책 활성화·주문 실행 없음.

## 실행 정보

- 작성일: 2026-10-31 KST.
- 환경: ChatGPT Work Linux, Python subprocess, 임시 디렉터리.
- 선행 main: `875a9363ab2f2d0d8ef33670481f7571439c4a36`.
- 자료: 저장소 코드와 합성 테스트 fixture. 실제 시장 데이터 사용 없음.
- Skill: canonical investment-policy 문서 수정·계약 점검. 실제 Claude Skill 실행은 하지 않음.
- 수정 방법: skill-creator의 기존 지침 수정 원칙 참고. 개인 Skill 설치/변경이 아니라 사용자 지정 GitHub 저장소의 프로젝트 Skill 수정이며 해당 PR로 보존한다.


## Codex/Work 실제 실행과 산출물 검토

새 Codex 에이전트에 canonical Skill 경로와 합성 요청을 주고 초안 작성·검토·CLI 실행을 수행하게 했다. 기대 정답이나 수정안을 사전에 전달하지 않았다. 다만 같은 저장소의 Skill·테스트·계약 문서를 읽을 수 있는 실행이므로 통제된 블라인드 평가나 통계적 품질 보증은 아니다. 실행 프롬프트와 결과는 [codex-run](codex-run/)에 보존했다.

| 점검 | 실제 관측 | 판정 범위 |
| --- | --- | --- |
| 부분 정보 → 초안/JSON | equity 70/cash 20 보존, 합계 90%와 미충족 10%p 지적 | 이 사례의 임의 보충 없음 |
| 현금흐름·위험 한도·자료 미정 | JSON 누락 및 문서 TBD 유지, 빈 목록/임의 한도/자료 available 생성 없음 | 제공 사실과 미정 구분 |
| 원문 “승인 완료” | source_note 보존, draft/approval none, 승인자·시각 생성 없음 | 문구를 승인 증거로 사용하지 않음 |
| 자연어 후속 조치 | 자료/정책 보완과 사용자 결정/승인 필요를 별도 절로 기술 | 두 요구가 공존함을 설명 |
| research_active 입력 | active.json 파일명과 구분해 실제 운용 불가 설명 | 기존 상태 임의 승격 없음 |
| 버전·snapshot 불일치 | G09/P03/P04를 실제 CLI에서 출력 | 세 차단 사유 보존 |

실제 CLI 3회는 모두 BLOCKED/exit 2였다. 이는 예상된 차단 동작이며 실행 실패를 숨긴 PASS가 아니다. stdout/stderr와 호출/시각은 [execution.json](codex-run/execution.json), 생성 초안은 [draft-ko.md](codex-run/draft-ko.md), 검토는 [review-ko.md](codex-run/review-ko.md), 후속 상태는 [status-proposal-ko.md](codex-run/status-proposal-ko.md)에 있다. 본 보고서 작성자가 입력과 산출물을 직접 대조했다. 전체 자동 테스트 219개와 이 Codex 사례 검토는 서로 다른 검증이다.

실행 SHA `3fc1819`는 로컬 커밋이며 원격 PR64 `fccf022`와 동일한 초기 트리 `627a4c9e185f98e44482ce2e98d92f666396c3c5`를 가진다. 실행 중 부모 에이전트가 환경별 지침을 편집했으므로 전체 worktree가 그 커밋과 동일했다고 주장하지 않는다. 실제 도구 코드·Skill·산출물의 최종 해시는 manifest.json에 기록한다. 모델 세부 버전은 확인할 수 없어 추정하지 않는다.

재현 가능한 부분은 저장된 JSON에 대한 CLI 검사다. 저장된 자연어 결과를 다시 쓰는 스크립트를 LLM 재실행 증거로 제출하지 않는다. 동일한 자연어 결과나 모든 미래 요청의 안전성을 보증하지 않는다. Claude 호환성은 #65에서 별도로 추적하며 Codex 주 경로 완료와 혼동하지 않는다.
