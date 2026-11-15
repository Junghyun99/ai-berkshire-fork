# 주식·채권·환율의 과거 버전 점검

2026-11-15 KST · 과거 자료 가용성 연구 · 기존 전략 성과 재계산 전 단계

## 연간 학습창 대조

기존 5자산 실험의 2017~2026년 1월 리밸런싱을 대상으로 했다. 학습 60개월과 신호 공백 2개월에서 필요한 수익률 60개는 월말 수준값 61개로 계산한다. 월초 이틀 전 날짜의 ALFRED 보관본을 사용한다. 이는 연구용 날짜 기준이며 최초 공표 시각을 인증하지 않는다.

| 입력 | 대조 범위 | 결과 |
| --- | --- | --- |
| USD/KRW DEXKOUS | 10개 학습창 × 월말 관측 61개 | 610건 전부 기존 원본과 날짜·값 일치 |
| NASDAQ100 TR NASDAQXNDX | 2026-01 학습창의 월말 관측 61개 | 61건 전부 기존 원본과 날짜·값 일치 |
| NASDAQXNDX의 2017~2025 결정시점 | 9개 보관일 요청 | HTTP 404, 대조 불가 |

수준값 양 끝이 일치한 비교 구간의 월 수익률도 같다. 나머지 자산의 동일성을 확장해 추정하지 않는다. 성공한 비교는 ALFRED와 기존 FRED 자료 사이의 버전 대조다.

ALFRED의 NASDAQXNDX 메타데이터는 제목·출처·릴리스 이력의 시작을 2025-07-30으로 표시한다. 앞선 9개 날짜 요청의 실패와 일관된다. 과거 지수값의 현재 조회 가능성과 과거 FRED 배포 이력은 다른 증거이므로, 2025년 이전에는 Nasdaq 원발행 자료나 다른 당시 아카이브가 추가로 필요하다. 지수 자체가 2025년에 처음 존재했다고 해석하지 않는다. [ALFRED 메타데이터](https://alfred.stlouisfed.org/series?seid=NASDAQXNDX)

연준 H.10 안내는 전주 일별 환율을 월요일 16시 15분에 공개하고 공휴일에는 다음 영업일에 발표한다고 설명한다. 관측일과 공표일에 차이가 있으므로 당일 환율을 즉시 알고 있었다는 가정은 사용할 수 없다. 이번에 사용한 오래된 학습월의 값은 보관본에서 직접 확인했다. [H.10 공표 안내](https://www.federalreserve.gov/releases/h10/)

## ETF 가격과 분배의 남은 증거

| 기존 입력 | 이번 확인 | 과거 버전 검증 상태 |
| --- | --- | --- |
| SPY | 발행사 페이지의 NAV 이력·분배 이력 경로 확인 | 원 실험의 Yahoo 수정가격이 각 과거 결정시점에 어떻게 제공됐는지 미확인 |
| IEF | 발행사 데이터 다운로드 및 기준일·분배락일·지급일·금액 항목 확인 | 원 실험의 수정가격 버전과 분배 발표시각 미확인 |
| KODEX 200 | 기존 공식 가격·분배 재구성 자료와 발행사 분배 이력 경로 확인 | 과거 파일 게시시각·개정 기록 미확인 |
| 148070 | 발행사 상품 페이지 조회 시도, 검색 결과는 존재하나 본문 요청 502 | 공식 장기 TR 및 당시 수정가격·분배 버전 검증 미완료 |

SPY Yahoo 이력 페이지의 이번 요청은 429였다. 이 응답만으로 공급자의 모든 경로가 접근 불가능하다고 판단하지 않는다. 현재 발행사 이력표는 값의 교차 대조에 사용할 수 있지만 과거 공개 버전을 인증하려면 날짜가 붙은 발표 원본과 수정 내역이 추가로 필요하다.

[SPY 발행사](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy) · [IEF 발행사](https://www.ishares.com/us/products/239456/IEF) · [KODEX 분배 이력](https://www.samsungfund.com/etf/product/distribution.do?tab=product) · [148070 발행사](https://www.kiwoometf.com/service/etf/KO02010200M?gcode=148070)

## 재현과 기록

[결과 JSON](results.json)에 요청 URL, 원문 해시, 실패 응답, 누락 및 차이를 저장했다. [스크립트](check.py)는 기존 snapshot-20261029의 manifest 해시를 검사하고 각 보관본의 월말 수준값을 Decimal로 대조한다. 월말부터 7일을 초과한 오래된 관측은 제외한다. 원 실험의 월말 추출 규칙과 같다.

기존 보관 파일 ai-berkshire-market-snapshot-20261029.zip에서 data/snapshot-20261029를 복원했다. ZIP 해시는 94853be0acb40192ab4548d2430d4888f0ce1c78155032e28ee9cfe44611e9e7이다. 새 FRED 전체 CSV는 최신 날짜가 추가돼 원본과 파일 해시가 달랐으므로 최종 비교에는 복원한 기존 원본을 사용했다. 기존 CSV의 해시는 저장소 source-manifest와 일치한다.

```bash
python3 reports/saa/20261115-asset-vintages/check.py --snapshot /path/to/snapshot-20261029 --work-dir /path/to/audit
```

작업 디렉터리 raw에 원문과 오류 응답을 캐시한다. 실패 경로를 새로 요청하려면 대응하는 .error.json 캐시를 지운다. 공개 재배포 조건이 확인되지 않은 Nasdaq 원문은 PR에 포함하지 않았다. 출처는 Nasdaq via FRED/ALFRED와 Federal Reserve Board via FRED/ALFRED다. 자료 수집·비교는 Codex/Work에서 수행했다.

동일한 환율과 확인된 NASDAQ 구간에서는 이번 버전 대조에 따른 학습 수익률 변화가 없다. 전체 5자산 입력의 가용성 인증은 ETF 과거 버전과 NASDAQ 초기 보관 이력이 미해결이므로 진행 중이다. 다음 실질 과제는 SPY·IEF의 가격·분배 원본을 공식 기록과 대조해 필요한 과거 정보가 복원 가능한지 확인하는 것이다.
