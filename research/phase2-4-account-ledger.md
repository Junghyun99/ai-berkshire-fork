# 계좌 현금 이벤트와 내부 이체 대조

2026-11-13 KST. Phase 2-4 연구 도구. [현금흐름 계산 계약](phase2-4-cashflow-performance-contract.md)과 [계산 코어](phase2-4-cashflow-core.md)에 연결한다.

`python3 tools/portfolio_ledger.py --input ledger.json` 또는 `tools.portfolio_ledger.normalize(payload)`로 실행한다. 예시는 합성 자료다.

```json
{"schema_version":"account-ledger-0.1","scope_id":"demo-v1","quality":"synthetic_fixture","accounts":["ISA","pension"],"events":[
  {"id":"a","account":"ISA","kind":"transfer_out","counterparty":"pension","transfer_id":"T","at":"2025-01-02T10:00:00+09:00","amount":"-20","currency":"KRW","status":"actual","source_ref":"fixture-a"},
  {"id":"b","account":"pension","kind":"transfer_in","counterparty":"ISA","transfer_id":"T","at":"2025-01-03T09:00:00+09:00","amount":"20","currency":"KRW","status":"actual","source_ref":"fixture-b"}
]}
```

포함 계좌는 익명 ID로 지정하고 구성 변경 시 scope_id 버전을 바꾼다. 입력은 사후 대조용 단일 스냅샷이다. 각 이벤트에 출처 참조, 계좌 내 고유 ID, 시간대가 있는 경제적 발생시각, 확정 상태, 부호 있는 십진 문자열 금액을 기록한다. quality는 actual_observed, research_proxy, synthetic_fixture 중 선언값이다. 실제 원본은 비공개로 보관한다.

| 기록 | 통합 처리 |
| --- | --- |
| deposit / withdrawal | 자료에서 범위 밖 상대임을 확인해 counterparty를 external로 지정한다. 통화별 external_flows에 납입/인출을 출력한다. |
| transfer_out / transfer_in | 같은 transfer_id의 출금 한 건과 입금 한 건을 대조한다. 상대 계좌가 서로 일치하고 통화·원금이 같으며 출금이 입금보다 늦지 않아야 한다. |
| fee / tax / dividend / interest | 비용·세금은 음수, 소득은 양수로 정규화 원장에 남긴다. 평가액에서 반영한 비용·소득을 외부 흐름에 더하지 않는다. |

예시의 통합 외부 흐름은 빈 객체다. transfers에 원금 20과 이체중 구간이 남는다. 평가 시각이 **출금 이상, 입금 미만**이면 출금·입금 계좌 잔고에서 빠진 원금을 이체중 자산으로 한 번 반영한다. 실제 NAV 구성과 중복 검사는 후속 평가 단계에서 수행한다. 시각은 UTC로 출력한다.

같은 계좌·ID의 동일 정규화 기록은 한 번 반영한다. 충돌, 출처 참조 누락, 상대 불명, 중복·누락 이체 다리, 금액/시각 모순, 환전 근거가 필요한 이종 통화 이체는 BLOCKED와 종료코드 2를 반환한다. 이체 수수료는 별도 비용 기록이 필요하다. 입력 범위를 자를 때 양쪽 다리 모두 포함해야 한다. 대조 완료 후 외부 흐름을 성과 측정 기간으로 제한한다.

external_flows의 통화별 목록은 해당 통화 Dietz 입력의 flows와 호환된다(흐름이 없으면 빈 배열). start/end NAV·시점은 호출자가 제공하고 기존 계산기의 기간·동시시각 검사가 적용된다. TWR에는 외부 흐름 전후 NAV, MWR에는 평가 달력의 날짜 변환이 추가로 필요하다. 원천 완전성·출처 인증, 증권사 파일 변환, FX와 계좌별 평가액 집계는 후속 작업이다. 실제 계좌 성과는 미검증이다.

합성 회귀는 내부 이체·비용·납입의 계산기 연결, 원장 순서·중복, 통화별 분리, 고정밀 원금, 대조 실패 및 CLI를 검사한다.
