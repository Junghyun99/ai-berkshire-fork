# 계좌별 순자산과 이체 중 원금의 통합 평가

2026-11-14 KST. [계좌 원장 계약](phase2-4-account-ledger.md)의 대조 결과를 사용한다. 연구용 사후 평가이므로 원장의 나중 입금 기록을 사용해 과거 이체 구간을 확인할 수 있다. 역사적 의사결정용 가용시점 검사는 별도 작업이다.

## 실행

아래 합성 입력을 파일로 저장해 `python3 tools/portfolio_nav.py --input snapshot.json`으로 실행한다. Python에서는 `tools.portfolio_nav.value(payload)`를 호출한다.

```json
{
  "schema_version": "portfolio-nav-0.1",
  "scope_id": "fixture",
  "at": "2025-01-02T00:00:00Z",
  "ledger": {
    "schema_version": "account-ledger-0.1",
    "scope_id": "fixture",
    "accounts": [
      "A",
      "B"
    ],
    "quality": "synthetic_fixture",
    "events": [
      {
        "id": "1",
        "status": "actual",
        "source_ref": "fixture",
        "currency": "USD",
        "transfer_id": "T",
        "account": "A",
        "counterparty": "B",
        "kind": "transfer_out",
        "amount": "-2",
        "at": "2025-01-02T00:00:00Z"
      },
      {
        "id": "1",
        "status": "actual",
        "source_ref": "fixture",
        "currency": "USD",
        "transfer_id": "T",
        "account": "B",
        "counterparty": "A",
        "kind": "transfer_in",
        "amount": "2",
        "at": "2025-01-03T00:00:00Z"
      }
    ]
  },
  "snapshots": [
    {
      "source_ref": "fixture",
      "quality": "synthetic_fixture",
      "account": "A",
      "at": "2025-01-02T00:00:00Z",
      "net_by_currency": {
        "USD": "8"
      },
      "booked_transit": {}
    },
    {
      "source_ref": "fixture",
      "quality": "synthetic_fixture",
      "account": "B",
      "at": "2025-01-02T00:00:00Z",
      "net_by_currency": {
        "KRW": "1000",
        "USD": "0"
      },
      "booked_transit": {}
    }
  ],
  "fx": {
    "source_ref": "fixture",
    "quality": "synthetic_fixture",
    "pair": "KRW_per_USD",
    "rate": "1000",
    "observed_at": "2025-01-02T00:00:00Z",
    "available_at": "2025-01-02T00:00:00Z",
    "max_age_seconds": 0
  }
}
```

예시의 송금 계좌에는 8 USD, 수취 계좌에는 1,000 KRW가 있다. 출금된 2 USD가 이동 중이므로 통합 잔액은 10 USD와 1,000 KRW다. 합성 환율 1,000 KRW/USD에서 평가액은 11,000 KRW와 11 USD다.

## 기준과 출력

- `ledger`에 #83의 입력 원장을 넣는다. 범위와 이체 기록 대조를 통과한 경우에만 평가한다.
- `snapshots`는 같은 기준시각에 범위 내 각 계좌당 하나씩 제공한다. 각 계좌가 보유한 모든 통화의 순액(평가한 투자자산·현금·미수금에서 부채 차감)을 원 통화별로 넣는다. 생략 통화는 잔액 0으로 해석한다. 증권사 환산 총액과 원 통화별 금액을 중복 입력하면 안 된다.
- `booked_transit`은 이미 순액에 포함된 이체 미수금을 이체 ID와 원 통화 금액으로 신고한다. 비어 있으면 계상액이 없는 것으로 처리한다. 출금 시각 이상, 입금 시각 미만인 대조 완료 이체 중 미계상 원금만 더한다. 미수금은 해당 송금/수취 계좌 중 하나에서만 전액 계상할 수 있다. 중복·부분 계상은 차단한다.
- `fx`는 양의 KRW per USD 단일 호가다. 관측시각 ≤ 가용시각 ≤ 평가시각을 검증한다. 허용 관측 경과시간은 호출자가 초 단위로 명시한다. KRW = 원화 순액 + 달러 순액 × 환율, USD = KRW / 환율. Decimal로 계산하며 USD 나눗셈은 유효숫자 34자리다.
- 성공 출력은 계좌 합계, 통화별 이체 조정액, 활성/이미 계상된 이체 ID, 환율·계좌 출처 참조, 양 통화 순자산을 담는다. 입력 중 synthetic_fixture가 있으면 결과도 synthetic_fixture, 그 다음은 research_proxy다. 자료의 진위 및 누락 없는 잔고 신고는 별도 대조가 필요하다.
- 실제 계좌 수집·개별 보유종목 가격 산출·이종 통화 이체·시장 환율 수집은 후속 범위다. 실계좌 원본은 비공개 경로에서 관리한다. `BLOCKED`는 종료코드 2와 사유를 반환한다.

## 검증

합성 자료를 사용해 출금·입금 경계, 이체 중 미수금 중복/부분 계상, 환율 변화, 계좌 누락·중복·시각 불일치, 환율 방향·가용시각·유효기간, 불완전 원장, CLI를 검증했다. 2026-11-14 Work 실행에서 `python3 -W always::ResourceWarning -m unittest discover -s tools/tests` 전체 298개가 통과했다. 다음 검증에는 같은 시각의 계좌별 원본 평가명세와 출처가 확인된 환율 스냅샷이 필요하다.
