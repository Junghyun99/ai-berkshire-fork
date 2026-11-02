# 연구용 정책 등록의 신뢰 경계와 복구 계약

작성일: 2026-10-31 KST. #51 구현, 선행 #59의 정책 입력 계약을 사용한다.

## 승인과 연구 등록

JSON의 `actor_type=user`, 사용자 이름, `POLICY_APPROVED` 문자열, 문서 해시는 실제 사용자의 신원이나 승인 행위를 인증하지 못한다. 외부 인증 경계는 아직 구현하지 않았다. 기본 `register(draft, event, directory)` 호출은 차단하며, 연구 시에만 `research_only=True` 또는 CLI `--research-only`를 명시한다. 이 옵션도 인증 수단이 아니다.

검사 중에만 후보를 active 형태로 구성해 기존 G01–G12 입력 검사를 실행한다. 저장·반환되는 결과는 `status=research_active`, `approval_authenticated=false`, `operational_use_allowed=false`다. 기존 `check_policy`와 제안 검증은 이를 실제 active 정책으로 인정하지 않는다. 실제 IPS v0.4는 DRAFT 상태 그대로다.

실제 운용으로 승격하려면 별도 신뢰 서비스에서 사용자 인증·정확한 정책 본문/버전 결속·승인 의사·철회·재사용 방지 등을 검증하고, AI가 수정할 수 없는 호출 경계를 설계해야 한다. 현재 도구에는 운용 승격 옵션이 없다. 단순 `authenticated=true` 입력을 추가해 인증으로 간주해서는 안 된다.

## 저장 계약

- POSIX 로컬 파일시스템, 한 디렉터리당 하나의 policy_id만 지원한다. 서로 다른 정책은 별도 디렉터리를 사용한다.
- `.registry.lock`의 OS advisory lock으로 참여 프로세스의 읽기/등록/복구를 직렬화한다. 프로세스 종료 시 잠금은 해제된다. 잠금 파일 자체는 삭제하지 않는다.
- `registry.json` 하나가 기준 원장이다. draft, 입력 이벤트, 연구용 정책, 직전 레코드 해시를 함께 보관한다. 임시 파일 flush/fsync → atomic replace → 디렉터리 fsync가 커밋 경계다.
- `policy-{version}.json`, `events.jsonl`, `active.json`은 원장에서 재생성할 수 있는 호환용 사본이다. active라는 파일명은 유지하지만 내용은 research_active다. 여러 사본을 한꺼번에 원자 교체하지는 않는다.
- 지원 독자는 `inspect_registry` 또는 CLI `show`를 사용한다. `show`는 사본 불일치 시 차단한다. 외부 프로그램이 파일을 직접 읽으면 기록 도중 서로 다른 세대를 관측할 수 있으므로 지원하지 않는다.
- 이벤트에 비어 있지 않은 `event_id`가 필요하다. 같은 ID·draft·event의 재시도는 한 레코드로 처리한다. 같은 ID의 다른 내용, 같은 버전의 새 이벤트는 차단한다. 과거 이벤트 재시도는 최신 current를 과거 버전으로 되돌리지 않는다.
- API/CLI 경로와 기존 입력 필드는 유지한다. 명시적 연구 모드, event_id, research_active 상태는 의도적인 안전 계약 강화이며 기존 호출자 수정이 필요하다. 기존 Skill을 자동 수정하지 않았으며 실제 런타임 연결 검증은 #52에서 수행한다.

## 실패, 감사, 복구

```bash
python3 tools/policy_registry.py register --registry /tmp/research-registry --policy draft.json --approval-event event.json --research-only
python3 tools/policy_registry.py audit --registry /tmp/research-registry
python3 tools/policy_registry.py recover --registry /tmp/research-registry
python3 tools/policy_registry.py show --registry /tmp/research-registry
```

커밋 전 실패는 직전 원장을 유지한다. 커밋 후 사본 기록 실패는 호출에 오류를 반환할 수 있어도 원장은 이미 저장됐을 수 있다. 같은 입력을 재시도하거나 audit 후 recover한다. 재시도에도 현재 날짜 기준 정책 검사가 적용되므로 만료된 입력은 recover를 사용한다. recover는 원장 해시/연결 검사에 성공한 경우에만 사본을 다시 쓴다. 예상 밖 archive 파일은 삭제하지 않고 오류 목록에 남긴다.

`audit`는 원장의 해시 연결, 중복 버전/이벤트, 연구 상태와 draft 해시, 사본의 내용·누락을 확인한다. `head_hash`를 외부에 별도로 고정하면 비교 기준으로 사용할 수 있으나 자동 외부 고정 기능은 없다. 원장과 해시를 모두 다시 쓰는 공격, 끝부분 삭제/이전 원장으로 롤백, 원장 전체 삭제를 단독 해시로 보장해서 탐지할 수 없다. 악의적인 작성자, 비협조 프로세스, 심볼릭 링크 공격, 네트워크 파일시스템, 디스크/전원 장애에 대한 플랫폼별 내구성 검증은 범위 밖이다. OS 권한과 외부 불변 저장소는 별도 과제다.

기존 archive/event/active 파일만 있고 새 원장이 없는 디렉터리는 자동 수입하지 않는다. 기존 파일을 보존한 채 별도 검토·마이그레이션이 필요하다는 오류로 차단한다. 임의 합성 승인으로 과거 기록을 채우지 않는다.

## 검증 범위

합성 fixture로 기본 호출 차단, 연구 상태의 운용 검증 차단, 이벤트 재시도/충돌, 버전 불변성, 프로세스 동시 접근, 커밋 전 실패, 각 사본 기록 실패, 변경 탐지/복구, 기존 디렉터리 보존을 검사한다. 이 테스트는 사용자 인증이나 실제 정책 활성화를 실행하지 않는다. 전체 수명주기(SUSPENDED/RETIRED 등)는 이번 등록·복구 구현에 포함하지 않는다.
