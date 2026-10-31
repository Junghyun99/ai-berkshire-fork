# 과거 가용시점·빈티지 선택 계약 및 차단 검사

기준일: 2026-11-01 KST. #54 부분 구현. **실제 과거 빈티지 수집·기존 백테스트 연결·재평가는 미완료**다. 새 자료를 만들거나 기존 available_at을 추정으로 채우지 않았다.

## 근거와 필드

FRED 공식 설명은 기본 조회와 과거 정보 집합을 구분하고 realtime_start/end로 과거 기간을 지정한다. vintagedates는 값이 새로 나오거나 수정된 날짜를 제공한다. 이 날짜형 응답만으로 장중 공개 시각·우리 공급망의 최초 가용시각을 인증하지 않는다.

- [FRED Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
- [FRED series/vintagedates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)

위 공식 문서를 확인했으나 실제 시리즈의 ALFRED 과거 값/API 호출은 이번 작업에서 수행하지 않았다. 예제 API 키를 실제 키처럼 사용하거나 공개 날짜를 임의 시각으로 바꾸지 않는다.

| 필드 | 이 도구의 정의 | 현재 자료에 대한 상태 |
| --- | --- | --- |
| observation_at | 해당 관측 대상의 기준 시점, timezone 포함 | 현재 CSV as_of는 날짜만 있어 자동 변환 금지 |
| vintage_at | 그 버전의 값이 공개된 시점 | 최신 스냅샷만 보유, 역사적 버전별 근거 미확보 |
| available_at | 해당 버전이 지정한 공급 경로에서 이용 가능해진 시점 | 기존 1,254행 모두 누락 |
| retrieval_at | 해당 버전을 이번 저장소가 수집한 시각 | 기존 manifest에 수집 시각 존재, 과거 가용일을 대신하지 않음 |
| vintage_id | 출처 내 버전 식별자 | 수집기/아카이브가 제공해야 함 |
| source_url / evidence_ref | 출처와 공개/가용시점 증거 참조 | 문자열 존재만 검사, 진위 인증은 안 함 |
| decision_at | 해당 연구 의사결정의 정보 컷오프 | 새 도구 호출자가 timezone 포함 명시 |

이 최소 계약은 이미 관측된 자료만 다룬다. 관측시점 이후에 공개되는 통계/마감값을 대상으로 observation <= vintage <= available <= retrieval을 요구한다. 예측치/사전발표 추정치는 별도 계약이 필요하다. 단위·TR/FX·상품 동일성 검증은 #53 계약의 별도 책임이며 이 선택기의 PASS가 대신하지 않는다.

## 입력별 확보 계획

| 입력 | 보유 상태 | 필요한 다음 증거 |
| --- | --- | --- |
| NASDAQXNDX | FRED 최신 TR 계열 | 시리즈별 빈티지 제공 여부, 수정된 과거 값, 공개 시각/배포 규칙 |
| DEXKOUS | FRED 최신 환율 | 발표일/시각·휴일 달력 및 수정 이력; fixing과 관측일 분리 |
| DGS3MO | FRED 최신 3개월 국채 금리 | 해당 시리즈 공개 일정·과거 버전; 월말 마지막 관측값의 최초 가용시점 |
| IR3TIB01KRM156N | OECD/FRED 최신 은행간 월 금리 | 최초 월별 발표/수정일·시각, OECD/FRED 배포 시차 |
| SPY/IEF | 공급자 최신 수정가격 | 과거 당시 조정가격/분배/분할 버전 또는 당시 원본에서 재구성한 근거 |
| KODEX 200 | 현재 보존 공식 가격·과거 분배표 | 당시 공시 공개시점·개정 이력; PDF 게시일과 분배 기준일 구분 |
| 148070 | 보완 공급자의 최신 수정가격 | #53 공식 장기 원본 및 역사적 분배/조정·공표 이력 |

어떤 시리즈도 이 표만으로 과거 시각이 인증됐다고 판단하지 않는다. 값이 바뀌지 않았다고 가정해 retrieval_at을 과거로 복사하지 않는다.

## 새 검사기

`tools/saa_availability.py`의 `select(records, decision_at, required)`는 명시적 series_id/observation_at 키를 요구한다. 모든 입력의 시각·증거 참조·유한 숫자를 검사하고 available_at이 cutoff보다 늦은 행을 제외한다. 가용한 후보 중 최신 vintage_at을 선택하며, 뒤늦게 들어온 구버전이 새 버전을 밀어내지 않는다. 같은 빈티지 ID의 값/시점 충돌과 같은 순위의 다른 값은 차단한다. 필수 관측이 빠지면 BLOCKED다.

같은 시각을 서로 다른 timezone으로 표시해도 UTC로 비교한다. 날짜만 있는 입력, timezone 없는 시각, UNKNOWN은 차단한다. 날짜 수준만 확인된 자료는 향후 보수적 일 경계/다음 세션 정책과 근거를 별도로 설계해야 하며 이번 구현은 그런 시간을 만들어 넣지 않는다.

반환은 `quality=research_proxy`, `evidence_authenticated=false`, `scope=declared_timestamp_selection_only`다. 입력으로 선언된 시각에 따른 선택만 검사하며 신원/원천 인증 또는 실제 당시 체결 가능성을 보증하지 않는다. retrieval_at이 decision_at 이후인 아카이브는 허용하지만 과거 시각을 입증하는 증거가 진짜인지는 별도 검토해야 한다. 전체 입력에 미확인 시각이 하나라도 있으면 보수적으로 차단한다.

```bash
python3 tools/saa_availability.py --input evidenced-vintages.json --decision-at 2020-02-03T00:00:00Z
```

입력 JSON은 records와 required 배열을 가진다. 정확한 합성 예시는 `tools/tests/test_saa_availability.py`다. 이 예시를 실제 자료로 재사용하지 않는다. PASS exit 0 / BLOCKED exit 2를 출력한다.

## 검증 및 미완료

합성 회귀 테스트 13개를 추가했다: 월말 후 공표, UTC/KST 동시각·경계 직전, 수정 공개 전후 값 선택, 미래 수정이 과거 선택에 영향 없음, 뒤늦은 구버전, 누락/날짜형 시각, 시점 역전, 수집일 오용, 버전/동시값 충돌, 필수 관측 누락, 증거/숫자 오류, 입력 불변성·비인증 라벨, CLI 누락 차단.

전체 `python3 -W always::ResourceWarning -m unittest discover -s tools/tests -v`: **232 tests / OK / 0.717초, ResourceWarning 0건**. 기존 지연 가정의 백테스트 경로는 변경하지 않았다. 이 선택기를 매 리밸런싱의 학습 컷오프에 호출하는 엔진 연결, 실제 빈티지 수집/증거 확인 및 기존 가정과의 수치 비교는 남아 있다. 고정비중 경로의 의사결정과 성과 평가용 관측 시점도 분리해야 한다.

#54는 부분 완료로 유지한다. 이 도구의 합성 테스트 통과는 기존 연구의 시점 누수를 제거했다는 뜻이 아니다. 자료 접근 제약 때문에 그 밖의 연구를 중단하지 않되, 기존 결과는 latest-vintage/research_proxy 라벨을 유지한다.

## 실행 정보

2026-11-01 KST, Codex/Work Python. 선행 #68 데이터 감사 위에서 구현. 공식 출처 문서는 위 2개, 수치 입력은 합성 fixture만 사용. 실제 시계열/시장가격 생성 없음, 실데이터 백테스트 재실행 없음, 정책 DRAFT 및 주문 금지 유지.
