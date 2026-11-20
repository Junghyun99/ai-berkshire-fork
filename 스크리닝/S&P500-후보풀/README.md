# S&P500 후보풀

S&P500 구성종목 503개(위키백과 구성종목표, 2026-11-20 조회 — 이중 상장주 GOOGL·GOOG 등 포함)를 대상으로 한 가치투자 후보 선별 작업 폴더.

## 스크리닝 흐름

1. **부실 배제(/quality-screen)** — 7개 정량 지표 + 3개 면제 규칙 → [`S&P500-부실배제결과-20261120.md`](S&P500-부실배제결과-20261120.md)
2. 통과 기업 심층연구(/investment-research, /investment-team) — 미착수
3. 밸류에이션 판단 — 미착수

## 재현

```bash
python3 tools/quality_screen_us.py --index SP500 --as-of 2026-11-20 --overrides "스크리닝/S&P500-후보풀/overrides-20261120.json"
```

[`overrides-20261120.json`](overrides-20261120.json)에는 결과 보고서에서 근거를 밝힌 수작업 판단을 모아 두었다.

- `not_young`: 면제 A에서 뺀 종목
- `costco_type`: 면제 C 적용 종목
- `dilution_ok`: ⑦ 비희석 사유 판정
- `cell_override`: ④ 신뢰 불가 처리

`_`로 시작하는 키는 기록용이다. 도구는 이 키를 읽지 않는다.

**결과 보고서와의 차이.** 결과 보고서는 도구를 만들기 전에 임시 스크립트로 계산했다. 도구는 한국 스크리닝과 같은 정의(`quality_screen_kr.compute_metrics`·`judge`)를 쓴다. 정의가 다른 부분은 다음과 같다.

- ④ 매출총이익률: 보고서는 5년, 도구는 10년
- ③ 이자보상 경계(⚠️): 보고서는 2.5배 미만, 도구는 3배 미만
- 데이터 부족: 도구는 ①이 데이터 부족이거나 데이터 부족 칸이 2개 이상이면 '판정 보류'로 둔다
- 금융업 ⑥: 도구는 판정하지 않는다

2026-11-20 같은 시점으로 다시 돌리면 결과는 통과 323 · 면제 통과 9 · 판정 보류 6 · 배제 162 · 데이터 부족 3이다. 보고서와 판정이 다른 14개는 아래와 같다. **기준은 결과 보고서**이고, 다음 스크리닝부터는 도구 결과를 쓴다.

| 종목 | 보고서 → 도구 | 원인 |
|---|---|---|
| DIS, CIEN | 배제 → 통과 | ① 8.0%·③ 2.2배가 정의 차이로 경계(⚠️) 안쪽 |
| KDP | 배제 → 통과 | ④·⑥ 장기 평균 기간 차이 |
| UNH | 배제 → 통과 | ⑥ 10년 순이익률 4.93% → 5.1%(비지배지분 포함 순이익) — 경계선 사례 |
| CARR | 통과 → 배제 | ⑤ OCF/NI 0.69(경계 바로 아래) |
| INVH, WELL | 통과 → 배제 | ③ 이자보상 0.5배·1.9배 — REIT 영업이익 근사(세전이익+이자) 차이 |
| TKO, NVR, V, HCA, FDXF, ARE | 통과 → 판정 보류 | 데이터 부족 칸 2개 이상(④ 원가 미구분 + ③·⑦ 등) |
| SKYD | 데이터 부족 → 배제 | 도구는 최신 회계연도가 2년 전(2024)이어도 판정한다 |

## 1차 결과 요약

통과 328 · 면제 통과 9 · 배제 162 · 데이터 부족 4 (통과율 67.0%)

## 대상 명단 (섹터별, 1차 결과 표시)

✅ 통과 · 🟡 면제 통과 · ❔ 데이터 부족 · ❌ 배제

| 섹터(GICS) | 종목 수 | 종목 |
|---|---|---|
| 산업재 | 83 | ✅ADP, ✅ALLE, ✅AME, ✅AOS, ❌AXON, ❌BA, ❌BE, ✅BR, ✅CARR, ✅CAT, ❌CHRW, ✅CMI, ✅CPRT, ✅CSX, ✅CTAS, ❌DAL, ❌DD, ✅DE, ✅DOV, ✅EFX, ❌EME, ❌EMR, ✅ETN, ✅EXPD, ✅FAST, ❌FDX, ✅FDXF, ✅FERG, ✅FIX, ✅FTV, ✅GD, ❌GE, ❌GEV, ✅GNRC, ✅GWW, ✅HII, ✅HON, ✅HUBB, ✅HWM, ✅IEX, ❌IR, ✅ITW, ❌J, ✅JBHT, ✅JCI, ✅LDOS, ✅LHX, ✅LII, ❌LMT, ❌LUV, ✅MAS, ✅MMM, ✅NDSN, ✅NOC, ✅NSC, ✅ODFL, ✅OTIS, ✅PAYX, ✅PCAR, ✅PH, ✅PNR, ❌PWR, ✅ROK, ✅ROL, ✅RSG, ✅RTX, ✅SNA, ❌SWK, ✅TDG, ✅TT, ✅TXT, ❌UAL, ❌UBER, ✅UNP, ✅UPS, ✅URI, ✅VLTO, ✅VRSK, 🟡VRT, ✅WAB, ✅WM, ✅XYL, ❔HONA |
| 금융 | 76 | ✅ACGL, ✅AFL, ❌AIG, ✅AIZ, ✅AJG, ✅ALL, ✅AMP, ✅AON, ✅APO, ✅ARES, ✅AXP, ✅BAC, ✅BEN, ✅BLK, ✅BNY, ✅BRK.B, ✅BRO, ✅BX, ❌C, ✅CB, ✅CBOE, ❌CFG, ✅CINF, ✅CME, ✅COF, ✅COIN, ✅CPAY, ✅EG, ✅ERIE, ✅FDS, ❌FIS, ✅FISV, ✅FITB, ✅GL, ❌GPN, ✅GS, ✅HBAN, ✅HIG, ❌HOOD, ✅IBKR, ✅ICE, ❌IVZ, ✅JKHY, ✅JPM, ✅KEY, ✅KKR, ❌L, ✅MA, ✅MCO, ❌MET, ✅MRSH, ✅MS, ✅MSCI, ✅MTB, ✅NDAQ, ✅NTRS, ✅PFG, ✅PGR, ✅PNC, ✅PRU, ✅PYPL, ✅RF, ✅RJF, ❌SCHW, ✅SPGI, ✅STT, ✅SYF, ❌TFC, ✅TROW, ✅TRV, ✅USB, ✅V, ✅WFC, ✅WRB, ✅WTW, ❌XYZ |
| IT | 76 | ✅AAPL, ✅ACN, ✅ADBE, ✅ADI, ✅ADSK, ✅AKAM, ✅AMAT, ❌AMD, ✅ANET, ✅APH, ✅AVGO, ✅CDNS, 🟡CDW, ❌CIEN, ❌COHR, ❌CRM, ❌CRWD, ✅CSCO, ✅CTSH, ❌DDOG, ❌DELL, ✅FFIV, ✅FICO, ❌FLEX, ❌FSLR, ✅FTNT, ✅GDDY, ✅GEN, ✅GLW, ❌HPE, ✅HPQ, ✅IBM, ❌INTC, ✅INTU, ✅IT, ❌JBL, ✅KEYS, ✅KLAC, ❌LITE, ✅LRCX, ✅MCHP, ✅MPWR, ❌MRVL, ✅MSFT, ✅MSI, ✅MU, ❌NOW, ✅NTAP, ✅NVDA, ✅NXPI, ❌OKTA, ❌ON, ✅ORCL, ❌P, ❌PANW, ❌PLTR, ✅PTC, 🟡Q, ✅QCOM, ✅ROP, ❌SMCI, ✅SNDK, ✅SNPS, ✅STX, ✅SWKS, ✅TDY, ✅TEL, ✅TER, ✅TRMB, ❌TWLO, ✅TXN, ✅TYL, ✅VRSN, ❌WDAY, ❌WDC, ✅ZBRA |
| 헬스케어 | 60 | ✅A, ✅ABBV, ✅ABT, ✅ALGN, ✅AMGN, ❌BAX, ❌BDX, ✅BIIB, ✅BMY, ✅BSX, ❌CAH, ❌CI, ❌CNC, ✅COO, 🟡COR, ❌CRL, ❌CVS, ✅DGX, ✅DHR, ✅DVA, ✅DXCM, ❌ELV, ❌EW, ✅GEHC, ✅GILD, ✅HCA, ❌HSIC, ❌HUM, ✅IDXX, ❌ILMN, ✅INCY, ✅IQV, ✅ISRG, ✅JNJ, ✅LH, ✅LLY, ❌MCK, ❌MDT, ✅MRK, ❌MRNA, ✅MTD, ✅PFE, ❌PODD, ✅REGN, ✅RMD, ✅RVTY, ✅SOLV, ❌STE, ✅SYK, ✅TECH, ✅TMO, ✅UHS, ❌UNH, ✅VEEV, ✅VRTX, ❌VTRS, ✅WAT, ✅WST, ❌ZBH, ✅ZTS |
| 경기소비재 | 47 | 🟡ABNB, ✅AMZN, ✅APTV, ✅AZO, ❌BBY, ✅BKNG, ❌CCL, ✅CMG, ❌CVNA, ❌DASH, ✅DECK, ❌DHI, ✅DPZ, ✅DRI, ❌EBAY, ❌EXPE, ❌F, ❌GM, ❌GPC, ✅GRMN, ❌HAS, ✅HD, ✅HLT, ✅LEN, ✅LOW, ✅LULU, ✅LVS, ✅MAR, ✅MCD, ✅MGM, ❌NCLH, ✅NKE, ✅NVR, ✅ORLY, ❌PHM, ❌RCL, ✅RL, ✅ROST, ✅SBUX, ✅TJX, ✅TPR, ✅TSCO, ❌TSLA, ✅ULTA, ✅WSM, ❌WYNN, ✅YUM |
| 필수소비재 | 33 | ❌ADM, ✅BF.B, ❌BG, ❌CASY, ✅CHD, ✅CL, ✅CLX, 🟡COST, ✅DG, ❌DLTR, ✅EL, ❌GIS, ✅HRL, ✅HSY, ❌KDP, ❌KHC, ✅KMB, ✅KO, 🟡KR, ✅MDLZ, ✅MKC, ✅MNST, ✅MO, ✅PEP, ✅PG, ✅PM, ❌SJM, ✅STZ, 🟡SYY, 🟡TGT, ❌TSN, ❌WMT, ❔VYLR |
| 유틸리티 | 31 | ❌AEE, ✅AEP, ❌AES, ❌ATO, ❌AWK, ❌CEG, ✅CMS, ❌CNP, ✅D, ✅DTE, ❌DUK, ❌ED, ❌EIX, ❌ES, ❌ETR, ❌EVRG, ❌EXC, ❌FE, ✅LNT, ✅NEE, ❌NI, ❌NRG, ❌PCG, ❌PEG, ❌PNW, ❌PPL, ❌SO, ❌SRE, ❌VST, ✅WEC, ❌XEL |
| 부동산 | 30 | ✅AMT, ✅ARE, ✅BXP, ❌CBRE, ✅CCI, ❌CPT, ❌CSGP, ❌DLR, ❌DOC, ✅EQIX, ✅ESS, ✅EXR, ✅FRT, ✅HST, ✅INVH, ❌IRM, ✅KIM, ✅MAA, ✅O, ✅PLD, ✅PSA, ✅REG, ✅SBAC, ✅SPG, ✅UDR, ✅VICI, ✅VMRK, ❌VTR, ✅WELL, ✅WY |
| 소재 | 24 | ❌ALB, ✅AMCR, ❌APD, ✅AVY, ❌BALL, ✅CF, ✅CRH, ❌DOW, ✅ECL, ✅FCX, ❌IFF, ❌IP, ✅LIN, ❌LYB, ✅MLM, ❌MOS, ❌NEM, ✅NUE, ✅PKG, ✅PPG, ✅SHW, ✅STLD, ❌SW, ✅VMC |
| 커뮤니케이션 | 22 | ✅APP, ✅CHTR, ✅CMCSA, ❌DIS, ❌ECHO, ✅FOX, ✅FOXA, ✅GOOG, ✅GOOGL, ❌LYV, ✅META, ✅NFLX, ❌NWS, ❌NWSA, ❌OMC, ❌RDDT, ✅T, ✅TKO, ✅TMUS, ❌TTWO, ✅VZ, ❔SKYD |
| 에너지 | 21 | ❌APA, ❌BKR, ✅COP, ✅CVX, ✅DVN, ✅EOG, ❌EQT, ❌EXE, ❌FANG, ❌HAL, ❌KMI, ❌MPC, ✅OKE, ✅OXY, ❌PSX, ❌SLB, ✅TPL, ❌TRGP, ❌VLO, ✅WMB, ❔XOM |

섹터는 위키백과 구성종목표의 GICS 섹터다. 금융 섹터의 은행·보험·증권·자산운용은 ②③④⑤가 N/A라서 통과 의미가 약하다.
