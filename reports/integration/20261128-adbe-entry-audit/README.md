# 어도비 첫 차수의 가격 조건과 11월 27일 중간 평가

2026-11-28 KST 연구. 2026-11-27 미국 정규장 종가까지 소급 재생했다. 첫 차수 기준은 250달러 이하, 가이던스 전 1%다. 분모와 실제 보유·현금이 확인되지 않아 아래 성과는 투입금 단위 가격수익으로 제한한다.

## 평가 시작점

보고서 기준가는 10월 30일 종가 250.23달러였다. 실행 계획 완성 커밋 b86c12d는 11월 2일 04:01:41 UTC에 작성됐고, main의 첫 반영은 065a0f6(11월 4일 14:12:35 KST, 미국 동부 00:12:35)이다. 완성 커밋과 main의 보고서 본문은 같은 blob이다. 이 연구는 main 반영 이후부터 관측한다. 11월 2일 시가 249.96과 11월 3일 종가 246.14는 이미 가격선 아래였으나 이 규칙에서는 제외한다. 브랜치 커밋 시각만으로 당시 외부 공개·열람 시각까지 확인할 수 없다.

[당시 main 보고서 §7](https://github.com/Junghyun99/ai-berkshire-fork/blob/065a0f6363a32df1d963c36a74f5c6135181a080/reports/어도비/최종보고서.md#L152)

## 사업 조건과 확정 범위

당시 보고서는 매수 ★3, 유기 ARR 성장 약 8.3% 추정이며 FY27 가이던스를 기다리는 상태였다. 1차는 가이던스 확인 전 가능한 차수이고 FY27 가이던스 +7% 및 유기 ARR +8%의 동시 확인은 4차 조건이다. Adobe의 9월 10일 Q3 발표는 공식 자료이며 회사 전체 ARR 수치만으로 Semrush 제외 유기 성장 추정치를 독립 검증할 수 없다. 11월 4~6일에 새로운 반증 공시가 없었다는 완전한 시점별 공시 검증, 가용 현금, 미사용 차수는 미확인이다. 따라서 아래는 당시 보고서 판단이 유효하고 첫 차수가 미사용이었다는 조건부 재생이다.

[Adobe Q3 발표](https://www.adobe.com/cc-shared/assets/investor-relations/pdfs/01906202/au56y4ter.pdf) · [SEC 제출본](https://www.sec.gov/Archives/edgar/data/796343/000079634326000147/adbeex991q326.htm)

## 가격 재생

| 미국 거래일 | ADBE 시가 | ADBE 종가 | 확인 사항 |
|---|---:|---:|---|
| 11-04 | 248.30 | 248.48 | main 반영 뒤 첫 시가·종가 모두 250 이하 |
| 11-05 | 250.59 | 246.44 | 전일 종가 신호 후 시가 한도 초과. 장중 체결을 가정하지 않음 |
| 11-06 | 239.00 | 239.30 | 직전 종가 신호와 시가 한도 모두 충족 |
| 11-27 | — | 234.79 | 중간 평가 종가 |

| 소급 모의 규칙 | 기준 진입 | ADBE | 같은 시각 SPY | 차이 |
|---|---|---:|---:|---:|
| 보고서 반영 후 첫 적격 시가 | 11-04 | −5.441% | −4.544% | −0.897%p |
| 종가 확인 후 다음 시가에서 한도 재확인 | 11-06 | −1.762% | −0.885% | −0.877%p |

두 방식은 동일한 11월 27일에 평가했다. SPY 진입 시가는 각각 762.99와 734.82, 종료 종가는 728.32달러다. USD 가격 기준으로 분배금·거래비용·세금·환전은 미반영이다. 이자 0 현금 대비 차이는 ADBE 가격수익률과 같다. 짧은 한 사례에서 진입 규칙 간 결과 차이는 진입 가격과 시장 노출 기간 차이를 함께 반영한다. 실제 체결·운용성과는 확인되지 않았다.

가격은 2026-11-28 열람한 Stock Analysis 표를 사용하고 QuiverQuant와 ChartExchange·Yahoo 페이지에서 주요 관측값을 대조했다. 공급자들의 기초 데이터 피드 독립성은 미확인이다. 11월 3일 ADBE 시가는 출처 간 0.01달러 차이가 있으며 계산에 사용하지 않았다. [ADBE Stock Analysis](https://stockanalysis.com/stocks/adbe/history/) · [ADBE QuiverQuant](https://www.quiverquant.com/stock/ADBE/historical-prices/) · [SPY Stock Analysis](https://stockanalysis.com/etf/spy/history/) · [SPY ChartExchange](https://chartexchange.com/symbol/nysearca-spy/historical/) · [SPY Yahoo](https://finance.yahoo.com/quote/SPY/history/)

재현 명령은 저장소 루트에서 `python3 reports/integration/20261128-adbe-entry-audit/verify.py`다. 날짜별 공개 여부는 `git log --first-parent --reverse -- reports/어도비/최종보고서.md`와 완성 커밋의 blob을 대조한다.
