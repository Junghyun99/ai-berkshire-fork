# 한국 단기금리 보관본과 연간 리밸런싱 학습창 대조

2026-11-14 KST. 대상은 [5자산 기본 실험](../20261029-korea-rebuild/results-summary.json)이다. 2017-01부터 2026-01까지 매년 1월에 비중을 정하는 일정에서 학습 60개월, 직전 2개월 제외, 금리 관측월 3개월 지연을 적용했다. 따라서 1월 결정의 마지막 학습월은 전년 10월이고 마지막 원금리 관측월은 전년 7월이다.

월 시작일 이틀 전의 ALFRED 날짜별 보관본을 택했다. 미국 날짜와 한국 월초의 경계가 겹치지 않게 한 연구용 기준이다. 보관일 이후 월초까지의 개정이나 실제 장중 결정시각은 검증 범위 밖이다. CSV 두 번째 열의 빈티지 날짜를 확인하고 관측월별 값을 Decimal로 비교했다. 비교 원본은 다시 받은 FRED CSV이며 바이트 해시가 [기존 수집 manifest](../20261029/source-manifest.json)와 일치한다.

| 결정 연월 | 원금리 관측월 범위 | 보관본 | 누락 / 값 차이 | 원문 SHA-256 |
| --- | --- | --- | --- | --- |
| 2017-01 | 2011-08 ~ 2016-07 | [2016-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2016-12-30) | 0 / 0 | `45f1f651db6ff0fb946aa0a681232136b5f07a02a5e7f3fc1fcb4cb6a3835b7b` |
| 2018-01 | 2012-08 ~ 2017-07 | [2017-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2017-12-30) | 0 / 0 | `1f3bc28ca9ed62b29a21a229d56d04f6c38084b25fe4db21dd0efb61b3a7f190` |
| 2019-01 | 2013-08 ~ 2018-07 | [2018-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2018-12-30) | 0 / 1 | `b639fe231dbce8eb3c9aea1c4d80cbbc2e4d212bcd3f6f865b7bd503e241342b` |
| 2020-01 | 2014-08 ~ 2019-07 | [2019-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2019-12-30) | 0 / 1 | `27457db9d3ad605184b826c7847544024780ee989d17c97864418f7ae21481e4` |
| 2021-01 | 2015-08 ~ 2020-07 | [2020-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2020-12-30) | 0 / 0 | `5d2e7707443f4d56bfadd5f6785b3f0fad1f8092eff38779a7ac189c0cc43208` |
| 2022-01 | 2016-08 ~ 2021-07 | [2021-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2021-12-30) | 0 / 0 | `c9c3e1a3fe28fbc624eb3b3ebbfaf123a6e200d76cf77fa2ccf20072ac3846b5` |
| 2023-01 | 2017-08 ~ 2022-07 | [2022-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2022-12-30) | 0 / 0 | `bd0670750289b3b985b039ef20c671427ad750ca7d7b003eb46f38b5bcb601ee` |
| 2024-01 | 2018-08 ~ 2023-07 | [2023-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2023-12-30) | 0 / 0 | `c77cfb1df85f095d87d7dd2ca69fec89c35c154e7cf8fc99cf4f361bc1a46897` |
| 2025-01 | 2019-08 ~ 2024-07 | [2024-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-12-30) | 0 / 0 | `2c54e4d1a2fb554f4fa176d090f3468afac0532f022960a020166c09a99da21e` |
| 2026-01 | 2020-08 ~ 2025-07 | [2025-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2025-12-30) | 0 / 0 | `7ea1ea4af3a4f300667e445020741f8c190ec70d7047a6b772eab26e4d8fb0f1` |

학습창 10개에서 총 600건(중복 월 포함)을 확인했다. 2019년과 2020년 학습창에서 같은 2014-08 관측이 당시 연 2.517%, 수집 원본 연 2.52%였다. 연율 0.003%p 차이는 월 추정 수익률로 0.00025%p다. 2024-01 관측은 2024-01 결정 이후의 값이며 2025-01과 2026-01 학습창에서는 모두 3.74%였다.

## 3개월 지연의 월별 점검

2024년 관측월 12개를 각각 3개월 뒤 적용월에 대응시켰다. 연간 학습에 들어간 시점과 월별 현금수익률 프록시를 적용하는 시점은 다르다.

| 관측월 | 적용월 | 보관본 | 연율(%) |
| --- | --- | --- | ---: |
| 2024-01 | 2024-04 | [2024-03-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-03-30) | 행 없음 |
| 2024-02 | 2024-05 | [2024-04-29](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-04-29) | 3.69 |
| 2024-03 | 2024-06 | [2024-05-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-05-30) | 3.65 |
| 2024-04 | 2024-07 | [2024-06-29](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-06-29) | 3.57 |
| 2024-05 | 2024-08 | [2024-07-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-07-30) | 3.60 |
| 2024-06 | 2024-09 | [2024-08-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-08-30) | 3.60 |
| 2024-07 | 2024-10 | [2024-09-29](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-09-29) | 3.54 |
| 2024-08 | 2024-11 | [2024-10-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-10-30) | 3.50 |
| 2024-09 | 2024-12 | [2024-11-29](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-11-29) | 3.52 |
| 2024-10 | 2025-01 | [2024-12-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2024-12-30) | 3.43 |
| 2024-11 | 2025-02 | [2025-01-30](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2025-01-30) | 3.42 |
| 2024-12 | 2025-03 | [2025-02-27](https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=IR3TIB01KRM156N&vintage_date=2025-02-27) | 3.35 |

12개 중 11개는 해당 보관본에 있었다. 1월 값은 [4월 9일과 10일 사이에 보관본에 등장](kr-rate-202401.md)했다. 다른 연도의 월별 평가 구간까지 확대해 해석할 수는 없다.

## 전략 판단에 미치는 범위

[비중 계산](../../../tools/saa_backtest.py)에서 위험균형과 동일가중은 학습 금리로 비중을 정하지 않는다. 이 금리 차이 자체가 두 전략의 비중을 바꾸지는 않는다. 최대 Sharpe 전략은 학습 금리를 사용하므로 해당 두 결정의 목표 비중에 영향이 있었는지는 별도 계산이 필요하다. 실현 Sharpe와 Sortino는 평가월 금리에 의존한다. 이번 조사는 새로운 성과값을 산출하지 않았다. 장중 공개시각이나 다른 자산 수익률의 당시 가용성을 인증하지 않는다.
