# Phase 2-2 — SAA 자산군 데이터·자본시장 기대치(CMA) 설계

- 작성일: 2026-10-28
- 상태: **데이터 파이프라인 초안 및 오프라인 계산 MVP**. 실제 시세 다운로드/기대수익률 확정/백테스트 **미실시**.
- 상위 문서: `research/phase2-1-strategic-asset-allocation-methodology.md`
- 정책 입력: `reports/policies/ai-berkshire-primary/draft-v0.4-2026-10-28.md` (DRAFT; 실제 운용 승인 아님)
- 목표: 동일한 검증된 시장 데이터로 MVO, 최소분산, 리스크 패리티, 고정 비중 모델을 비교하도록 **재현 가능한 데이터 계약과 통계 산출 과정**을 정한다.

## 1. 데이터 파이프라인

```text
시장 가격·분배/배당·FX·금리·ETF 메타데이터
 → [Raw Snapshot: 원본 불변 보관, 출처/검색·공개시각 기록]
 → [Corporate Action & Distribution Adjustment]
 → [Asset Exposure Map: 상장국가 vs 기초자산/헤지/레버리지]
 → [Return Normalization: KRW primary / USD secondary]
 → [Data Quality Gate: 시점·결측·휴장·통화·총수익 검사]
 → [Aligned Asset-Class Return Panel]
 → [Realized Metrics: 변동성·상관관계·공분산]
 → [CMA: 시나리오/모델별 기대수익·위험, 불확실성 포함]
 → [Phase 2-3 Optimization & OOS Validation]
```

CFA Institute는 기대수익/공분산을 과거 평균만으로 정하지 말고 데이터 품질, 모델 불확실성과 시계열·횡단면 일관성을 검토하라고 설명한다.[1][2]

## 2. 경제적 노출 단위와 투자상품 단위 구분

**연구 자산군(초기 후보, 아직 확정 SAA 아님)**

| 경제적 자산군 | 예시 프록시 후보 | 예시 상품의 주의점 |
|---|---|---|
| 국내 주식 | KOSPI200 총수익 계열 | 가격지수와 배당 포함 지수 구분 |
| 미국 대형주 | S&P500 총수익 계열 | QQQ는 미국 대형주 전체가 아닌 NASDAQ100 편향 |
| 미국 성장/기술주 | NASDAQ100 총수익 계열 | 미국 대형주와 중복 노출 큼 |
| 미국 외 글로벌 주식 | MSCI ACWI ex USA 등 총수익 계열 | 지수 라이선스/데이터 취득 가능성 확인 |
| 국내 국채 | 국내 국채 총수익 지수 | 만기/듀레이션, 쿠폰 반영 |
| 미국 국채 | 미국 국채 총수익 지수 | 듀레이션·환헤지·FX 영향 |
| 원화 현금성 | 한국 단기금리/현금성 총수익 | 금리 시계열 자체는 투자 수익 지수가 아님 |
| 달러 현금성 | 미국 단기금리 기반 현금 수익 지수 | 한국 거주자 KRW 환산 시 FX 반영 |
| 기타 방어자산 | 금/리츠 등 (필요성 검증 후) | 기초 상품·배당·보관/환헤지 제약 확인 |

**반드시 분리할 속성:** `listing_market`, `trading_currency`, `underlying_asset_class`, `underlying_country_weights`, `fx_exposure`, `hedge_ratio`, `leverage_daily_target`, `account_eligibility`.

- **국내상장 해외주식 ETF**는 상장 한국 / 기초 해외주식으로 집계. KRW 거래가 환위험 부재를 뜻하지 않는다.
- **레버리지 ETF**는 투자상품 구현/위험 오버레이의 별도 레이어에서 취급. 단순히 2배 연 수익률이나 분산을 기초자산 역사에 곱하지 않는다.
- 프록시 지수를 동일한 실제 ETF의 과거 이력으로 잘못 가장하면 상장 이전 성과를 왜곡한다. 프록시는 연구용 모델로만 표시.

## 3. 출처 우선순위

| 종류 | 1차 후보 | 검증/대체 | 우선 확인 |
|---|---|---|---|
| 지수 총수익 | 지수 산출기관의 공식 TR series | 제공사 검증된 데이터 | Price vs TR, Net vs Gross, 라이선스 |
| 주식/ETF 가격 | 거래소/운용사·발행사 공식 자료 | 기존 `global_stock_data.py`의 Yahoo 계열 | 분할·배당/분배·상폐·심볼 변경 |
| 국내 ETF 기초노출 | ETF 운용사·한국거래소 공개 정보 | PDF/공시 | 최신 구성비중, 환헤지/레버리지 |
| KRW/USD FX | 한국은행 ECOS·공식 고시/시계열 | 일관된 검증된 제공사 | 방향(KRW per USD), 고시/장 마감시점 |
| 무위험수익률 KRW | 국내 단기 무위험금리·국채 지표 | 한국은행/공식 자료 | 투자 가능 현금 수익과 다를 수 있음 |
| 무위험수익률 USD | 미국 T-bill/OIS 등 | `fred_data.py`, FRED/ALFRED | 관측치와 발표·수정 시점 분리 |
| 거시·시나리오 | 공식 중앙은행·통계기관 | FRED 빈티지 | 발표/관측일·개정치 확인 |

FRED 관측치 API는 `realtime_start/end`와 `vintage_dates`를 지원한다. 과거 시점 모형을 재현할 때는 **당시에 이용 가능했던 발표 값**을 사용해야 한다.[3]
Yahoo Adjusted Close는 배당·분할을 반영하지만, 지수의 Gross TR과 법적 세후 수익이 같다고 가정하지 않는다.[4]

**출처 채택 규칙:** (a) 지수 정의와 수익·배당 처리 확인, (b) 라이선스/재배포 가능 여부 확인, (c) 자료 개정 정책, (d) 기준일 접근 가능성. 공식 출처에 접근 못 하면 대체 근거와 품질 등급을 남긴다.

## 4. 표준 데이터 계약

### 4.1 asset_universe.csv (예시 열)

`asset_id,proxy_id,proxy_type,asset_class,listing_market,underlying_region,trading_currency,fx_hedged,leverage_daily_target,account_eligibility,source_url`

`proxy_type`: `official_total_return_index | etf_adjusted_price | modeled_proxy`; **프록시와 실제 거래상품을 혼동하지 않는다**.

### 4.2 monthly_returns.csv (MVP 필수 입력)

```csv
month,asset_id,total_return_local,fx_to_krw_return,source_id,as_of,available_at,quality
2025-01,US_EQ,0.02,0.01,example,2025-01-31,2025-02-03,illustrative
2025-01,KR_BOND,0.005,0,example,2025-01-31,2025-02-03,illustrative
```

- `total_return_local`: 해당 자산 기준통화 총수익률(소수, 분배 재투자 가정 출처 확인).
- `fx_to_krw_return`: **월간** 환율 수익률(예: KRW per USD의 월간 변화율); 원화 자산은 `0`.
- `available_at`: 투자자가 해당 데이터에 접근 가능하게 된 날짜. 백테스트 신호는 이 시점 이전에 사용 불가.
- `quality=illustrative`인 행은 **실제 정책 최적화 입력 금지**. `verified` 외 값은 검증 실패 처리.
- 통화 변환: `r_KRW = (1+r_local) × (1+r_FX) - 1`. USD 결과는 KRW 복합 총수익에서 USD/KRW FX 효과를 되돌리거나 자산별 USD 수익을 별도 계산한다.
- KRW/USD 변환은 현금흐름·기준통화와 동일한 월말 fixing을 사용한다. 서로 다른 월말 휴장일은 공식 캘린더로 정렬하여 계산.
- 월별 데이터는 **월말 스냅샷을 선호**하며, 첫 번째 유효 월의 수익 산출에는 선행 월말 데이터가 필요하다.

### 4.3 dataset_manifest.json

```json
{
  "dataset_id": "saa-cma-v0",
  "schema_version": "0.1",
  "generated_at": "2026-10-28T00:00:00+09:00",
  "as_of": "TBD",
  "frequency": "monthly",
  "primary_currency": "KRW",
  "secondary_currency": "USD",
  "return_basis": "total_return_before_personal_tax",
  "data_sources": [],
  "source_hashes": {},
  "price_convention": "official_tr_or_distributions_reinvested",
  "fx_convention": "KRW_per_USD_month_end",
  "universe_version": "TBD",
  "missing_policy": "reject_missing_months_in_shared_window",
  "lookahead_policy": "available_at <= decision_date"
}
```

운용 시 원본 데이터, 정규화 결과, manifest, 변환 코드 버전을 함께 보존한다.

## 5. 품질 게이트

| 코드 | 검증 | 실패 시 |
|---|---|---|
| D01 | 월/자산 ID 중복, 월 정렬, 월별 전 자산 관측 | BLOCKED |
| D02 | 수익률 유한값 및 `>= -100%`, 100% 초과 시 확인 | BLOCKED |
| D03 | 원천 시세·배당·분할과 총수익 정의 일치 | BLOCKED/REVIEW |
| D04 | FX 방향, hedge/currency와 실제 환노출 정의 일치 | BLOCKED |
| D05 | `available_at`이 `as_of`보다 먼저인 **과거 신호 사용 금지** | BLOCKED |
| D06 | 새로 상장된 ETF의 과거 지수 프록시 사용 시 명확한 `modeled_proxy` 표기 | BLOCKED |
| D07 | 월별 공통 관측기간과 최소 표본(예: 60개월 **연구용 후보값**) | 부족 시 미출고 |
| D08 | 누락 자산·대리 데이터·이상치/비정상 점프 보고 | 원인 미규명 시 BLOCKED |
| D09 | 계좌별 상품적격·IRP 관련 현행 규제 재확인 | 실제 배치 전 BLOCKED |
| D10 | 총수익/가격, 환율, USD 보조지표의 월별 복리 정합성 | BLOCKED |
| D11 | 실거래 데이터와 연구 시뮬레이션 데이터를 섞지 않음 | BLOCKED |
| D12 | 저작권/라이선스·재배포 가능성 확인 | 배포 중단 |

**D05 세부사항:** `as_of`는 수익률의 관측 월말이고 `available_at`은 공표·조회 가능일이다. 데이터 정규화 파일 보관 자체는 `available_at > as_of`여도 가능하지만, **해당 수익을 월말 당일의 신호로 사용하는 것은 금지**한다. (서로 다른 두 날짜를 동일 개념으로 검사하지 않는다.)

## 6. 추정과 평가 지표

- **실현 평균:** 단순 월 평균×12 (연환산 산술 기대치의 기술통계), 월별 복리 기하 CAGR과 구분.
- **실현 분산/공분산:** 월별 표본 공분산 ×12; 변동성 `sqrt(12) × stdev(monthly)`.
- **상관계수:** 표본 공분산을 표준편차로 나누며, 분산 0 자산은 상관 미정 처리.
- **장기 기대수익률(CMA):** 실현 평균을 그대로 미래 기대수익으로 채택하지 않는다. 배당·실질성장·밸류에이션 변화·금리/기간·위험프리미엄 기반 독립 시나리오와 결합한다. **확률/범위와 추정오차** 기록.[1][2]
- **공분산 안정화:** 표본 공분산 외 shrinkage·factor/sensitivity 시나리오를 비교한다. 추정 윈도·정규화·시장국면 변화에 강건한지 확인.[2]
- **CAGR/MDD/Sharpe/Sortino:** RF(통화/기간별)·MAR·무위험자산 기준·추정 방식 명시, 실제 포트폴리오 연구 단계에서 산출. Sharpe의 연환산 관행이 독립·동일분포 가정을 필요로 하는지 확인.
- **시간 분할:** 학습/검증/테스트, expanding/rolling window, 정보 이용 가능일 `available_at`을 사용한 walk-forward. 하이퍼파라미터를 시험 구간에 맞춰 재선택하지 않음.
- **인출/추가납입:** 포트폴리오 현금흐름은 시장 지수 수익률과 **구별**. 인출 재원 부족·계좌별 유동성은 별도 시뮬레이션.

## 7. MVP 오프라인 계산기

`tools/saa_data_quality.py`는 **실데이터 수집기가 아니다**. 기존 혹은 후속 ingestion 결과의 표준 CSV를 입력받아:

1. 행 단위 계약, quality 및 통화 변환을 검사한다.
2. 공통 월별 패널이 완전한지 확인한다.
3. KRW 수익률 패널의 월평균·연환산 표본 공분산·상관계수를 산출한다.
4. 검증 실패 시 nonzero exit code와 실패 이유를 출력한다.

**주의:** 이 결과는 실현 통계량이며 **미래 기대수익률 및 투자정책 승인을 의미하지 않는다**. 이 PR의 테스트는 오프라인용 예제 데이터로만 검사한다.

## 8. Phase 2-3 인계 및 실험 체크리스트

- (1) 공식/검증된 월간 자산군 총수익률 시계열을 수집, 월말 FX와 결합. 원본 해시 보존.
- (2) 실데이터의 유효 관측 기간·중복/결측·미상장·비총수익 프록시 문제를 보고.
- (3) baseline(시장·동일가중·고정혼합)과 MVO/최소분산/위험균형을 같은 시계열로 비교.
- (4) 인출·계좌제약·레버리지 ETF는 별도 Phase 2-4에서 현실화.
- (5) IPS v0.4는 DRAFT 유지; 어떤 시뮬레이션 결과도 자동 정책 활성화하지 않는다.

## 9. 검증 가능한 외부 출처

[1] CFA Institute, [Capital Market Expectations Part I (2026)](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/capital-market-expectations-part-i) — 기대치의 일관성·추정 오류·검증 절차.

[2] CFA Institute, [Capital Market Expectations Part II (2026)](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/capital-market-expectations-part-ii) — 주식/채권/FX 기대수익률·공분산·shrinkage 추정.

[3] FRED/ALFRED, [series/observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) — vintage 관측과 `realtime_start/end`.

[4] Yahoo Help, [Adjusted Close](https://in.help.yahoo.com/kb/adjusted-close-sln28256.html) — 배당·분할 조정 가격의 정의.
