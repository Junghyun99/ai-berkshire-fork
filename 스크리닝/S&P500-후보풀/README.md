# S&P500 후보풀

S&P500 구성종목 503개(위키백과 구성종목표, 2026-11-20 조회 — 이중 상장주 GOOGL·GOOG 등 포함)를 대상으로 한 가치투자 후보 선별 작업 폴더.

## 스크리닝 흐름

1. **부실 배제(/quality-screen)** — 7개 정량 지표 + 3개 면제 규칙 → [`S&P500-부실배제결과-20261120.md`](S&P500-부실배제결과-20261120.md)
2. 통과 기업 심층연구(/investment-research, /investment-team) — 미착수
3. 밸류에이션 판단 — 미착수

## 재현

현재 저장소만으로는 **재실행할 수 없다.** 7지표 계산은 SEC EDGAR XBRL companyfacts(10-K 원본)에서 `tools/sec_edgar_data.py`의 `values_as_of`를 재사용한 임시 스크립트로 했고, 그 스크립트는 저장소에 넣지 않았다.

[`overrides-20261120.json`](overrides-20261120.json)에는 결과 보고서에서 근거를 밝힌 수작업 판단을 모아 두었다. 금융업 N/A 범위, REIT ① 제외, 면제 A에서 뺀 종목, 면제 C 대상 업종, ⑦ 희석 사유 판정 24건, ④ 신뢰 불가 처리, 데이터 부족이 들어 있다. 미국 시장용 도구(`quality_screen_us.py` 등)를 만들면 이 파일을 입력으로 쓴다.

같은 날 작성한 [나스닥100 후보풀](../나스닥100-후보풀/README.md)은 `tools/quality_screen_kr.py`의 `compute_metrics`·`judge`로 판정했다. 두 결과는 계산 구현이 다르다. 겹치는 종목에서 대부분 같은 판정이 나왔지만 AMD(① 왜곡 보정)·AEP(② 설비투자 태그 보정)처럼 수작업 조정이 다른 사례가 있다.

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
