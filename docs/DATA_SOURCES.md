# AI Berkshire — SAA 데이터 출처 및 품질 계약

> 최초 작성: 2026-10-29. **수집 후보 목록이며 실제 데이터 다운로드·검증 완료 목록이 아니다.** 현재 확보된 CSV/검증된 장기 수익률 데이터셋이 있다고 가정하지 않는다.

## 최소 필요 데이터(Phase 2-3)

| 구분 | 자산/지표 | 1차 출처 후보 | 보조/연구용 프록시 | 주요 검증 |
| --- | --- | --- | --- | --- |
| 주식 TR | KOSPI200 (배당 포함) | 한국거래소 지수·공식 TR 제공 | **EWY** ETF는 한국 전체 주가 지수의 대체가 아님 | 공식 TR 여부·산출일·환율·ETF 비용 |
| 주식 TR | S&P500 / NASDAQ100 | S&P Dow Jones/나스닥 공식 총수익지수 | **SPY / QQQ** 수정 가격 | 상장일·배당 재투자·분배금 |
| 주식 TR | 미국 외 글로벌 주식 | MSCI 등 공식 총수익 지수 | 해당 지수 추종 ETF | 지수 라이선스·커버리지 |
| 국채 TR | 한국 국채 총수익지수 | KRX/한국채권평가 등 지수 제공사 | 국채 ETF | 쿠폰 재투자·듀레이션 |
| 국채 TR | 미국 국채 총수익지수 | Treasury 관련 총수익 제공기관 | **IEF / SHY** 수정 가격 | 듀레이션·배당·장기 프록시 |
| FX | USD/KRW | 한국은행 ECOS | [FRED DEXKOUS](https://fred.stlouisfed.org/series/DEXKOUS) | `KRW per USD` 방향/공표시각/월말 기준 |
| USD RF | 미국 3개월 단기 금리 | [FRED DGS3MO](https://fred.stlouisfed.org/series/DGS3MO) 또는 [GS3M](https://fred.stlouisfed.org/series/GS3M) | 직접 ETF 수익률과 혼동 금지 | 연율 금리를 기간 수익률로 변환 |
| KRW RF | 국내 단기 금리 | [한국은행 ECOS](https://ecos.bok.or.kr/) | 검증된 원화 단기상품 지표 | 기준금리 ≠ 실제 투자 가능 현금 수익 |
| ETF 구성 | 국내상장 해외주식형 ETF, 환헤지, 레버리지 | 운용사 상품 설명서·구성·거래소 공시 | 공개 거래 플랫폼 | 기초 노출·헤지·상장시장 분리 |
| 가격·매매 | 실제 거래 ETF 가격·분배금 | 운용사·거래소 | yfinance 등 | 조정종가 vs 총수익·상폐·생존자 편향 |

**공식 기관/제공사의 실제 API 주소, 시리즈 코드, 라이선스, 접근 가능 여부는 수집 시점에 확인해야 한다.** ECOS의 한국 국채 총수익 데이터나 ETF 전체 상품 가능 여부를 현재 확보했다고 주장하지 않는다.

## 수집 규칙

1. 가급적 **15~20년**의 일별 원시값을 확보하고 월간 공통 Total Return 패널로 정규화. 상장 전 과거는 실제 ETF 실적이라 표기 금지.
2. 원본 불변 보존 + `source_url, vendor, symbol/series_id, retrieval_at, observation_at, available_at, currency, units, license, sha256, quality` 기록.
3. 배당/분배/분할 재투자 조건·지수 Gross/Net/Price 유형 명시. 단순 Close 사용으로 총수익 과대/과소평가 방지.
4. 환율: 월별 현지통화 수익률과 FX 수익률 복리 결합 `(1+r_local)*(1+r_fx)-1`. USD/원화 보조 평가 각각 계산.
5. 달러/원화 각각 적절한 기준금리와 총수익 벤치마크를 사용. FRED 이자율 숫자를 직접 국채 투자 월간 수익률로 취급 금지.
6. 관측일(`as_of`)과 최초 가용일(`available_at`) 구분. 워크포워드 학습 시 **당시 가용했던 데이터**만 사용. 발표·수정 데이터는 FRED/ALFRED vintage 활용을 고려.
7. missing, duplicate, stale, biased sample, calendar alignment, suspension/상폐, 구성 교체, index methodology 변경 검사. 자료 길이가 짧으면 연구용 proxy 표시.
8. 수집·가공·테스트 성공 로그와 소스 라이선스가 없는 데이터셋은 **검증완료로 출고하지 않는다**. `quality=verified` 자체는 암호학적 인증이 아니다.

## 프로그램/산출물 현황

- `tools/saa_data_quality.py` (PR #38): 표준 월별 CSV 기본 검증·KRW 공분산/상관. **모든 D01~D12 구현 보장 아님**.
- `tools/saa_backtest.py` (PR #39): 검증 CSV 입력 월별 OOS 전략 비교 연구 엔진. **실제 데이터 평가 결과 없음**.
- 예상 산출물: `data/raw/<source>/...` (라이선스·용량·민감성 확인 후 저장여부 결정), `data/processed/monthly_returns.csv`, `data/manifest.json`, `reports/saa/<run-id>.md`. 이는 **권장 경로이며 현재 존재한다고 보장하지 않는다**.
- 이전 채팅에서 ZIP 수집 가이드를 만들어 공유했지만 **GitHub 커밋/실행 여부 확인 안 됨**. Work가 파일 접근 가능 시 소스 재검토하고 공식 파이프라인으로 전환할 것.
- 실데이터 사용 전 `README`, 데이터 출처, 기간, 품질 검사·hash, 실패 이유를 같은 PR에 남긴다.

## 공식 도구·문서 참고

- [FRED API 관측치/빈티지](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [FRED DEXKOUS](https://fred.stlouisfed.org/series/DEXKOUS)
- [FRED DGS3MO](https://fred.stlouisfed.org/series/DGS3MO)
- [한국은행 ECOS](https://ecos.bok.or.kr/)
- `research/phase2-2-saa-data-cma-design.md`(Phase 2-2 브랜치에서 확인).
