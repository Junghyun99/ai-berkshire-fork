# Phase 4 사례 — Microsoft를 줄여 어도비로 교체한 경우

2026-11-28 KST 소급 연구. [11월 4일 main의 MSFT 보고서](https://github.com/Junghyun99/ai-berkshire-fork/blob/065a0f6/reports/마이크로소프트/최종보고서.md#L140)와 [같은 버전의 ADBE 보고서](https://github.com/Junghyun99/ai-berkshire-fork/blob/065a0f6/reports/어도비/최종보고서.md#L152)를 사용했다. MSFT 축소선 511달러와 ADBE 첫 차수 상한 250달러를 전일 종가와 다음 정규장 시가에서 모두 확인한다. 두 문서를 함께 사용할 수 있는 첫 거래일인 11월 4일 종가부터 관측한다. 11월 5일 ADBE 시가 250.59달러는 한도를 넘었다. 5일 종가는 MSFT 535.93, ADBE 246.44였고 6일 시가는 각각 525.69, 239.00달러여서 두 조건이 함께 성립했다.

이 사례는 가격 조건의 교집합이다. MSFT 1주 분량의 미사용 축소 여유와 ADBE 1차 1%·이벤트 한도 내 여유, 실적 발표 후의 MSFT 논지 유지 및 ADBE 반증 부재를 가정한다. 실제 보유 비중·승인·체결은 미확인이다. 특히 [선행 축소 사례](../20261128-msft-trim-audit/README.md)처럼 이미 10월 29일 해당 차수를 사용했다면 같은 물량은 다시 팔 수 없다. 실제 두 판단을 차례대로 실행했다고 해석하지 않는다.

## 세 가지 대안

모두 11월 6일 시가 기준 MSFT 1주(525.69달러)에서 출발한다. 11월 20일 분석 개정 직전 거래일인 19일 종가에 평가한다. MSFT는 종가 498.30에 배당 권리 0.98달러를 더한다(배당락 19일, 지급 12월 10일). ADBE 종가는 221.68달러이고 이 기간 배당은 0으로 처리했다. 현금에는 11월 5일 미 3개월 국채 수익률 4.17%를 13일간 ACT/365 단리로 적용했다. 이는 예수금 실측 이자가 아닌 대용치다. 거래 비용은 거래당 거래대금의 0.25% 가정이며, 교체안은 매도대금에서 매도·매수 비용을 모두 충당한다. 분할주 허용, 세금·환전 제외, 종료일 보유분은 매도하지 않는다.

| 대안 | 종료 가치 USD | 수익률 | 구간 MDD |
|---|---:|---:|---:|
| MSFT 계속 보유 | 499.28 | −5.02% | −8.42% |
| MSFT 축소 후 현금 | 525.15 | −0.10% | −0.25% |
| MSFT 축소 후 ADBE 편입 | 485.16 | −7.71% | −9.89% |

MDD는 거래 전 최초 평가액과 이후 정규장 종가 10개에서 측정한 고점 대비 낙폭이다. 전체 포트폴리오나 장중 낙폭을 나타내지 않는다. 매도 기여(현금−유지) +25.87달러와 신규 매수 기여(교체−현금) −39.99달러가 합쳐져 교체 순효과는 −14.12달러, 최초 자금 대비 −2.69%p였다. 비용을 0으로 줄여도 교체−유지는 −11.69달러다. 이 구간에서 MSFT를 줄인 판단과 자금의 재투자 판단은 반대 방향으로 기여했다. 기간과 표본은 사후 선택했다.

11월 28일 조회한 원시 시세와 배당 권리를 사용했다. 두 가격표의 원천 피드 독립성은 미확인이다. [MSFT 시세](https://stockanalysis.com/stocks/msft/history/) · [MSFT 교차 대조](https://www.morningstar.com/stocks/xnas/msft/historical-data) · [ADBE 시세](https://stockanalysis.com/stocks/adbe/history/) · [ADBE 교차 대조](https://www.financecharts.com/stocks/ADBE/summary/price) · [Microsoft 배당 발표](https://news.microsoft.com/source/2026/09/15/microsoft-announces-quarterly-dividend-increase-7/) · [연준 H.15](https://www.federalreserve.gov/datadownload/Preview.aspx?pi=400&preview=H15%2FH15%2FRIFLGFCM03_N.B&rel=H15)

재현 명령은 저장소 루트에서 `python3 reports/integration/20261128-msft-adbe-switch/verify.py`다. 입력 일별 종가, 비용 민감도와 손익 차이의 합산 검사를 포함한다.
