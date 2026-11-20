# 나스닥100 후보풀

나스닥100 구성종목 101개(Nasdaq API, 2026-11-19 조회 — GOOGL·GOOG 이중 상장 포함, 실질 100개 법인)를 대상으로 한 가치투자 후보 선별 작업 폴더.

## 스크리닝 흐름

1. **부실 배제(/quality-screen)** — 7개 정량 지표 + 3개 면제 규칙 → [`나스닥100-부실배제결과-20261120.md`](나스닥100-부실배제결과-20261120.md)
2. 통과 기업 심층연구(/investment-research, /investment-team) — 미착수
3. 밸류에이션 판단 — 미착수

## 재현

```bash
python3 tools/quality_screen_us.py --universe "스크리닝/나스닥100-후보풀/universe-20261119.json" --as-of 2026-11-20   --overrides "스크리닝/나스닥100-후보풀/overrides-20261120.json"
```

- [`universe-20261119.json`](universe-20261119.json): 결과 보고서 요약표의 101종목이다. 원 출처는 Nasdaq API로 2026-11-19에 조회했다. Nasdaq API는 자동 요청을 막고 위키백과 나스닥100 문서에는 구성종목표가 없어서, 도구는 지수를 직접 조회하지 않고 이 파일을 쓴다.
- [`overrides-20261120.json`](overrides-20261120.json): 결과 보고서 '수작업 조정 (근거)' 표를 옮긴 것이다. ALAB ⑦의 상장 효과도 넣었다. 보고서에서는 '상장 5년 미만'으로 처리했고, 도구는 상장 전 연도까지 이어 붙여 +425%로 계산한다. GOOGL·GOOG ⑦은 도구가 희석 가중평균주식수로 직접 계산하므로(약 −7%) override하지 않았다.

같은 시점으로 다시 돌리면 결과 보고서와 판정이 모두 같다. 통과 67 · 면제 통과 5 · 배제 27 · 데이터 부족 2(SPCX·HONA)다.

## 1차 결과 요약

통과 67 · 면제 통과 5 · 배제 27 · 판정 보류 2 (판정 가능 99개 중 통과율 72.7%)

## 대상 명단 (섹터별, 1차 결과 표시)

✅ 통과 · 🟡 면제 통과 · ❔ 판정 보류 · ❌ 배제

| 섹터(GICS) | 종목 수 | 종목 |
|---|---|---|
| IT | 35 | ✅AAPL, ✅MSFT, ✅NVDA, ✅AVGO, 🟡AMD, ✅MU, ✅CSCO, ❌PLTR, ❌INTC, ❌PANW, ✅AMAT, ✅TXN, ✅LRCX, ❌CRWD, ✅KLAC, ✅ADI, ✅QCOM, ❌MRVL, ✅STX, ❌WDC, ✅SNDK, ✅FTNT, ✅ADBE, ✅CDNS, ✅INTU, ✅SNPS, ✅NXPI, ✅MPWR, ❌DDOG, ✅ADSK, ❌LITE, ✅ROP, ❌WDAY, ✅TER, ✅MCHP |
| S&P500 비편입(외국 기업 등) | 15 | ✅ASML, ✅ARM, ❌SHOP, 🟡PDD, ✅MELI, ✅CCEP, ✅TRI, ✅FER, 🟡ALAB, ❌MSTR, ❌RKLB, ❌NBIS, ❌CRWV, ❌ALNY, ❔SPCX |
| 산업재 | 11 | ✅ADP, ✅CSX, ✅CTAS, ✅HON, ✅FAST, ✅PCAR, ✅PAYX, ✅ODFL, ✅CPRT, ❌AXON, ❔HONA |
| 경기소비재 | 9 | ✅AMZN, ❌TSLA, ✅SBUX, ✅BKNG, ✅MAR, 🟡ABNB, ✅ORLY, ✅ROST, ❌DASH |
| 헬스케어 | 9 | ✅AMGN, ✅GILD, ✅ISRG, ✅VRTX, ✅REGN, ❌MRNA, ✅IDXX, ✅GEHC, ✅DXCM |
| 커뮤니케이션 | 8 | ✅GOOGL, ✅GOOG, ✅META, ✅NFLX, ✅TMUS, ✅APP, ✅CMCSA, ❌TTWO |
| 필수소비재 | 6 | ❌WMT, 🟡COST, ✅PEP, ✅MNST, ✅MDLZ, ✅KDP |
| 유틸리티 | 4 | ❌CEG, ❌AEP, ❌XEL, ❌EXC |
| 에너지 | 2 | ❌FANG, ❌BKR |
| 소재 | 1 | ✅LIN |
| 금융 | 1 | ✅PYPL |

섹터는 같은 날 조회한 S&P500 구성종목표의 GICS 섹터를 빌려 썼다. S&P500에 없는 종목(ASML·ARM·PDD 등)은 한 칸에 모았다. [S&P500 후보풀](../S&P500-후보풀/README.md)과 겹치는 종목이 많지만, 계산 구현과 수작업 조정이 달라 판정이 다를 수 있다.
