# Phase 2-4 현금흐름 계산 코어 — 구현 범위와 검증

2026-11-01 KST · RESEARCH_ONLY · IPS/평가 DRAFT 유지.
선행 #74 [전체 설계](phase2-4-cashflow-performance-contract.md)의 **집계 이후 순수 계산 부분**을 구현했다. 계좌 원장·이체중 자산·FX·시점 가용성 adapter는 아직 없다.

## 구현과 입력 경계

`tools/portfolio_cashflow.py`의 `calculate(payload)` 및 `--input` JSON CLI를 추가했다. 기존 `saa_backtest.py`, 정책 검증/등록, Skill, 과거 결과는 변경하지 않았다. 성공 종료코드 0은 연구 계산 가능, 차단은 2다. 정책 승인이나 원천 진위를 인증하지 않는다.

계산 입력은 이미 **하나의 scope·통화로 집계된 NAV와 외부 입출금**이다. 원시 계좌 레코드를 이 형식으로 자동 변환하지 않는다. 실제 계좌를 처리하려면 누락 계좌·자산·현금·이전·비용·FX·출처를 대조한 adapter가 필요하다. 입력의 source_ref와 quality는 선언값일 뿐이며 출력은 항상 evidence_authenticated=false / policy_approval_granted=false다.

| 항목 | 규칙 |
| --- | --- |
| schema_version | `cashflow-core-0.1` |
| method | `twr`, `dietz`, `mwr` 중 명시적 선택. 자동 fallback 없음 |
| scope_id / source_ref | 비어 있지 않은 문자열. 익명 범위 ID와 입력 근거 참조 |
| currency | KRW 또는 USD. 모든 NAV/금액은 이미 해당 통화여야 함 |
| quality | actual_observed / research_proxy / synthetic_fixture. 진위 인증 의미 아님 |
| start / end | `{at, nav}`; start<end, 시작 NAV>0, 종료 NAV≥0 |
| flows | `{id, at, amount, kind}` 목록; TWR만 before/after 필수 |
| amount / nav / before / after | 최대 128자 decimal 문자열, 유한값. bool·숫자형 JSON·지수 표기·NaN 거부 |
| kind | external_deposit 양수 / external_withdrawal 음수. 비용·배당·내부 이전은 허용하지 않음 |
| at | TWR/Dietz: timezone 포함 ISO 시각, UTC 정규화. MWR: 엄격 YYYY-MM-DD |
| date_basis | MWR 필수 비어 있지 않은 설명. 상위 변환기가 적용한 평가 timezone/달력 규칙을 기록하며 이 모듈이 변환하지 않음 |

목록 외 필드는 거부한다. 특히 흐름별 다른 통화, planned status, transfer_id를 무시하여 실제 외부 흐름으로 처리하지 않는다. 시나리오 계산은 별도 합성 입력으로 명시해야 한다. 이 입력에는 raw revision/available_at이 없으므로 실제 시점 누수를 검사하는 기능도 없다. 정규화 전 상위 계층에서 증거·revision을 검증하고 원본/변환 manifest 해시를 보존해야 한다.

외부 흐름의 허용 기간은 `(start,end]`. 시작 NAV는 시작 흐름 후, 종료 NAV는 종료 흐름 후다. 중복 id는 완전히 같은 레코드일 때 한 번만 반영하고 내용 충돌은 차단한다. TWR/Dietz에서 서로 다른 id의 동일 UTC 시각 흐름은 미지원으로 차단한다. 전체 설계의 group/sequence 처리는 후속 adapter 범위다. MWR은 같은 날짜의 투자자 현금흐름을 합산한다.

## 계산 구현

- TWR: 각 흐름의 `before + amount == after`를 Decimal로 검사한다. 비용은 흐름에서 빼지 않고 구간 NAV에서 반영한다. 구간별 `before/previous_after`를 기하 연결하고 마지막 NAV 구간을 포함한다. 종료시각 흐름이 있으면 after=종료 NAV를 요구한다.
- 전액 인출은 종료시각에서만 지원한다. 중간에 NAV=0인 뒤 재개하면 SEGMENT_ENDED다. 무흐름 경로의 종료 NAV=0은 -100%로 종결한다. 같은 시각 손실 소진 후 재납입을 연속 성과로 연결하지 않는다.
- Dietz: 명시적으로 선택한 경우만 시간 가중 흐름을 적용한다. exact TWR은 출력하지 않고 approximation=true다. 분모≤0이면 차단한다. 전체 설계의 큰 흐름 임계값은 아직 미정이며 이 결과를 정확 성과로 승격하지 않는다.
- MWR: 초기 NAV 음수, 외부 흐름 반대 부호, 종료 NAV 양수를 합산한다. ACT/365F로 일자를 사용한다. 합산 후 부호 변화가 1회인 경로만 허용한다. 0회는 NO_SIGN_CHANGE, 여러 번은 AMBIGUOUS_CASHFLOW_PATTERN이다. 후자는 복수근 존재를 항상 증명한다는 뜻이 아니다.
- MWR solver: y=log(1+r), [-32,32]에서 이분법 최대256회. 지수항 공통 스케일로 overflow를 줄인 상대 NPV 잔차≤1e-12를 요구한다. 브래킷 실패/불수렴/수치범위 오류를 구분한다. 탐색 밖 해는 ROOT_NOT_BRACKETED이며 전역 무해 판정이 아니다. 1년 미만은 기간 MWR를 주 표시한다. 연율/기간 값·일수·잔차·허용오차·반복수를 함께 출력한다.

## 합성 CLI 예시

아래는 화폐 단위만 KRW로 표시한 합성 산술값이며 실제 사용자 금액이 아니다.

```json
{
  "schema_version": "cashflow-core-0.1",
  "method": "twr",
  "scope_id": "synthetic-example",
  "currency": "KRW",
  "source_ref": "synthetic fixture",
  "quality": "synthetic_fixture",
  "start": {"at": "2025-01-01T00:00:00Z", "nav": "100"},
  "end": {"at": "2026-01-01T00:00:00Z", "nav": "231"},
  "flows": [{"id": "e1", "at": "2025-07-02T12:00:00Z", "amount": "100", "kind": "external_deposit", "before": "110", "after": "210"}]
}
```

`python3 tools/portfolio_cashflow.py --input /path/to/input.json` → twr=0.21, RESEARCH_ONLY. NAV 증가율 131%와 구분한다. 실제 실행 시 입력 파일·코드 커밋·출력 및 해시를 함께 보존한다.

## 검증 기록

- 환경: Codex/Work, Python unittest.
- `python3 -W always::ResourceWarning -m unittest discover -s tools/tests -v`: **258 tests / OK / 1.289초**, ResourceWarning 0건. 신규 26개 포함, GitHub CI 성공을 뜻하지 않는다.
- 신규: 입출금 TWR, 비용, 전후 NAV 불일치, 중복/충돌, UTC 동시각, 날짜만 입력, 비유한/잘못된 수치, 경계 흐름, 전액 인출/시장 손실, Dietz 분모, MWR 알려진 해/복수 부호/같은 날짜/브래킷 실패, 원장 필드 차단, CLI 성공·오류, 입력 불변성.
- 기존 #74 합성 산술 예시와 구별하여 실제 새 모듈을 호출했다. 실제 시장자료·개인 원장 테스트는 아니다.
- 상대 링크·git diff --check·report_audit extract dry-run 확인. dry-run은 데이터 진위 인증이 아니다.

## 미완료와 다음 단계

계좌별 이벤트 정규화·이전 두 다리/이체중 자산·FX·세금·현금 가용성·계좌 적격성·실제 snapshot·source hash 인증·#54 연결은 미구현이다. 단순 source_ref 입력으로 통합 포트폴리오 검증을 완료 처리하지 않는다. 기존 SAA 엔진과의 adapter 및 계좌/레버리지 제약도 미구현이다. #53~56, 사용자 선택은 계속 미결이다.

다음은 계좌별 이벤트를 통합 외부 흐름으로 정규화하는 원장/이전 대조와 입력 증거 계약이다. 실제 사용자 금액을 임의 생성하거나 납입 중단·인출 실패를 숨기지 않는다. 정책 활성화·주문은 수행하지 않는다. 병합 순서는 #73 → #74 → 이 구현 PR이다.
