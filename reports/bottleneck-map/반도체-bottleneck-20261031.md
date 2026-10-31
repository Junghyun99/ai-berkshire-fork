# 반도체 수요발 공급망 병목 스캔 — 2026-10-31

> 질문: "AI발 반도체 수요가 계속 커지면 어느 고리가 먼저 부족해지는가?"
> 범위: Layer 2~3(소재·부품·후공정 장비). GPU·HBM 본체·파운드리(Layer 1)는 가격 반영이 충분하다고 보고 기준점으로만 쓴다.
> 시세 기준: Yahoo Finance 조회값(2026-10-31 조회, 직전 거래일 종가 추정). 달러 환산은 추정 환율(USD/JPY 156, USD/KRW 1,450, USD/TWD 31, USD/HKD 7.8, EUR/USD 1.16)을 썼다.

---

## 0. 결론 요약

- **S급 병목은 세 곳이다. ① 저열팽창 유리섬유 원단(T-glass) ② ABF 필름·대형 AI용 IC 기판 ③ InP(인화인듐) 기판.** 세 곳 모두 2027년까지 수급 격차가 이어진다는 1차·2차 출처가 복수로 있다.
- **A급 병목은 HBM용 프로브카드**다. FormFactor와 Micronics Japan(MJC)이 HBM 수요로 사상 최대 매출을 냈고, Technoprobe CEO는 생산능력을 "극히 중요한 제약"이라고 말했다.
- **병목이 진짜인 것과 투자 기회인 것은 다르다.** IC 기판 대형주(Ibiden PER 85, Kinsus 167, Nan Ya PCB 147)와 한미반도체(PSR 32배, 2025 매출 +3%)는 밸류에이션 관문에서 걸렸다. InP의 AXT는 적자에 중국 수출허가 리스크가 겹쳐 ★★로 묶었다.
- **밸류에이션 관문을 통과해 심층 연구할 가치가 있는 종목은 두 곳이다. Micronics Japan(6871.T)과 Nitto Boseki(3110.T).** 두 회사 모두 최근 고점에서 40~57% 떨어진 상태다. 다만 하락 이유(독점 약화, 증설 지연)가 그대로 리스크이므로 매수 결론이 아니라 **심층 연구 대상**이다.
- 배경: 필라델피아 반도체지수(SOX)는 10월 초 8거래일 연속 하락했다(낙폭 11~16%, 출처마다 다름). 같은 달 SK하이닉스는 DRAM·HBM이 2029년까지 사실상 완판이라고 밝혔다. **수요 지표와 주가가 엇갈리는 구간**이다.

---

## 1단계: 슈퍼 트렌드 확인

```
트렌드 이름: AI 반도체 수요 (AI 인프라 구축의 반도체 하위 사슬)
핵심 동력: AI 학습·추론 수요가 GPU/ASIC·HBM·첨단 패키징 물량을 끌어올리고, 그 하위 소재·부품의 증설 속도가 따라가지 못함
이미 발생한 검증 이벤트:
  1. [2026-10-28] SK하이닉스 3Q26 매출 104.6조원, LTA·협의 물량 포함 DRAM·HBM 2029년까지 사실상 완판, 2027 capex 대폭 증가 [Korea Times, investinglive]
  2. [2026-10-20] 유니마이크론 회장: 장비 80% 이상 납기 연장, 일부 핵심 장비 30개월, 2027년 핵심 소재 20% 공급 부족 가능 [TrendForce]
  3. [2026-10-29] 인텔 3Q26 10-Q: 업계 전반의 기판·메모리 부족이 실적에 영향. 9월 CEO 발언으로는 CPU 공급이 수요의 약 절반 [SEC 10-Q, TrendForce]
  4. [2026-10-28] FormFactor 3Q26 매출 2.805억 달러, 가이던스 상단 초과 [SEC 8-K]
  5. [2026-10-29] AXT 3Q26 매출 7,340만 달러, 전년 대비 +162% [SEC 8-K]
자본지출 규모: 메모리·파운드리·패키징 capex는 연 수천억 달러 규모(추정). 기판 업계만 약 191억 달러의 증설을 계획 중 [BigGo/TSMC 발언 인용]
수급 격차 판단: 예. 하류 수요 증가 > 소재·장비 증설(납기 18~30개월)
트렌드 확인: ✅ 추적 가능
```

**반대 논거**: 10월 반도체주 급락 때 Broadcom CEO는 일부 AI 투자를 "도박"에 비유했고, CoreWeave 등 AI 클라우드 사업자의 부채 우려가 커졌다. BofA 설문에서는 "2027년 AI 버블 형성"이 컨센서스로 나왔다. 수요 둔화가 오면 병목 해소가 증설보다 **수요 쪽에서** 먼저 올 수 있다.

---

## 2단계: 공급망 물리적 분해

```
Layer 0: AI 학습/추론 서비스, AI 서버
Layer 1 (가격 반영 충분): GPU/ASIC(엔비디아·TSMC), HBM(SK하이닉스·삼성·마이크론), CoWoS, 서버 CPU
──────────────────────────────────────────────
Layer 2 (중점 스캔):
  ├─ 패키지 기판: 대형 ABF 기판(Ibiden·Unimicron·삼성전기·Kinsus·Nan Ya PCB), EMIB-T 기판
  ├─ 기판 소재: ABF 필름(Ajinomoto), 저CTE 유리섬유 원단 T-glass(Nittobo·대만유리·Baotek·Asahi Kasei), CCL
  ├─ 메모리 후공정: HBM TC 본더(한미반도체·한화세미텍·ASMPT), 하이브리드 본더
  ├─ 테스트: HBM/DRAM 프로브카드(FormFactor·MJC·Technoprobe), 테스트 소켓(ISC·리노공업)
  └─ 광인터커넥트: InP 기판 → EML/CW 레이저 (AXT·Sumitomo Electric·JX Advanced Metals)
Layer 3:
  ├─ PCB/기판 제조 장비(드릴·노광·도금): 납기 최대 30개월
  └─ 원료: 인듐, 고순도 유리 원료
Layer 4: 팹 부지·전력(용인 클러스터 등). 이번 범위 밖
```

---

## 3단계: 병목 식별

| 고리 | ①공급 집중 | ②증설 주기 | ③대체 난이도 | ④가동률 | ⑤수요 증가 | ⑥인증 주기 | 🔴 수 | 등급 |
|---|---|---|---|---|---|---|---|---|
| T-glass(저CTE 원단) | 🔴 Nittobo 약 90%(TrendForce, 2026.4) | 🔴 후쿠시마 신공장 2027 초, 3배 증설은 FY2029 | 🟡 대만유리 인증 완료, Asahi Kasei Q-glass | 🔴 풀가동 | 🔴 2026 진입 시점 수요 2배(보도) | 🔴 >1년 | 5 | **S** |
| ABF 필름 | 🔴 Ajinomoto 사실상 독점 | 🟡 | 🔴 유리코어는 장기 과제 | 🔴 2Q26 풀가동(Tom's HW) | 🟡 | 🔴 | 4 | **S** |
| 대형 AI ABF 기판 | 🟡 5~6개사 | 🔴 장비 납기 최대 30개월 | 🔴 | 🔴 | 🟡 공급 격차 2H26 약 10% → 2027 약 20%(Counterpoint) | 🔴 | 4 | **S** |
| InP 기판 | 🟡 3개사가 80~90% | 🔴 격차 해소에 2~3년 | 🔴 EML·CW 레이저 대체 불가 | 🔴 | 🔴 AXT 매출 +162% YoY | 🔴 | 5 | **S** |
| HBM 프로브카드 | 🔴 HBM은 FormFactor·MJC 양강(추정) | 🟡 1~2년(FORM 신공장 가동비 발생) | 🔴 | 🟡 "생산능력이 극히 중요한 제약"(Technoprobe CEO) | 🟡 | 🔴 | 3 | **A** |
| HBM TC 본더 | 🟡 한미·한화·ASMPT·SEMES | 🟢 장비는 1년 내 증설 가능 | 🟡 하이브리드 본딩은 2029~30년으로 지연 | 데이터 부족 | 🟡 | 🔴 | 1 | **B** |
| PCB/기판 제조 장비 | 데이터 부족 | 🔴 최대 30개월 | 데이터 부족 | 🔴 | 🟡 | 🟡 | 2 | **B**(데이터 부족) |
| 테스트 소켓 | 🟢 다수 | 🟢 | 🟡 | 데이터 부족 | 🟡 | 🟡 | 0 | 병목 아님 |
| 전력 반도체(PMIC·VRM·SiC) | — | — | — | — | — | — | — | 판정 보류(출처가 유통사 마케팅뿐) |

### 병목 지도

```
공급망 병목 지도 — AI 반도체 수요
갱신 날짜: 2026-10-31

S급 병목:
  1. T-glass(저CTE 유리섬유 원단) — 사실상 1개사가 공급, 신규 생산능력은 2027년부터 — Nittobo, (2위권) 대만유리·Baotek·Asahi Kasei
  2. ABF 필름 / 대형 AI ABF 기판 — 필름은 독점, 기판은 장비 납기 30개월 — Ajinomoto / Ibiden·Unimicron·삼성전기·Kinsus·Nan Ya PCB
  3. InP 기판 — 수율 15~20%, 중국은 주문마다 수출허가 필요 — AXT(중국 퉁메이), Sumitomo Electric, JX Advanced Metals

A급 병목:
  1. HBM/DRAM 프로브카드 — HBM4 전환으로 웨이퍼 테스트 수요 급증 — FormFactor, Micronics Japan, (진입 중) Technoprobe

B급 병목:
  1. HBM TC 본더 — 하이브리드 본딩 지연으로 수요 연장, 공급사는 늘어나는 중
  2. PCB/기판 제조 장비 — 납기는 길지만 공급사 구조 데이터 부족

최근 변화: 첫 스캔이라 비교 대상 없음
```

**병목 해소 신호(반대 논거)**:
- TSMC 측은 CoWoS 수급이 "매우 근접"했다고 말했다(BigGo 인용). 병목은 사라진 게 아니라 소재 쪽으로 **이동** 중이다.
- Nittobo는 2026년 8월 "추가 T-glass 가격 인상 계획 없음"을 밝혔다(TrendForce). 독점 공급사가 가격을 올리지 않는다는 것은 점유율 방어로 돌아섰다는 신호로 읽힌다(관점).
- Prismark는 대만유리 등의 증설을 합치면 T-glass 부족이 "다소 완화될 수 있다"고 봤다.
- InP는 서류상 생산능력이 수요의 약 2배다. 실제 판매 가능한 물량이 적은 이유는 수율과 수출허가다(Compound Semiconductor). 수율이 개선되면 병목이 빠르게 풀릴 수 있다.

---

## 4단계: 기업 선별

### 4.1 후보 전체와 1차 선별

| 회사 | 코드 | 시총(USD 환산 추정) | 병목 고리 | 순수도 | 1차 결과 |
|---|---|---|---|---|---|
| Nitto Boseki | 3110.T | 약 36억 달러 | T-glass | 전자재료 비중 데이터 부족(FY3/26 성장 동력) | ✅ |
| 대만유리 | 1802.TW | 약 58억 달러 | T-glass 2위권 | 유리섬유 부문 매출의 30%(2025), 저CTE는 그 일부 | ⚠️ 경계선 |
| Baotek | 5340.TWO | 약 5억 달러 | T-glass(Nittobo 자회사) | 유리섬유 원단 100%, 저CTE 비중은 데이터 부족 | ⚠️ 유동성 확인 필요 |
| Ajinomoto | 2802.T | 약 313억 달러 | ABF 필름 | ABF는 매출의 소수(식품 기업) | ❌ 순수도·시총 |
| Ibiden / Unimicron / 삼성전기 / Kinsus / Nan Ya PCB | — | 160억~660억 달러 | ABF 기판 | 높음 | ❌ 시총 >100억 달러, Layer 1.5로 이미 가격 반영 |
| AXT | AXTI | 약 40억 달러 | InP 기판 | InP 비중 수치가 출처마다 상충 | ✅ |
| Micronics Japan | 6871.T | 약 31억 달러 | HBM 프로브카드 | 프로브카드가 주력(추정 90%+) | ✅ |
| FormFactor | FORM | 약 68억~76억 달러 | HBM 프로브카드 | 프로브카드가 주력 | ✅ |
| Technoprobe | TPRO.MI | 약 198억 달러 | 프로브카드(로직 중심, HBM 진입 중) | 높음 | ❌ 시총 >100억 달러(참고용) |
| 한미반도체 | 042700.KS | 약 129억 달러 | TC 본더(B급) | 높음 | ❌ 시총·밸류에이션(참고용) |
| ASMPT | 0522.HK | 약 61억 달러 | TC 본더(B급) | 첨단 패키징은 일부 | ⚠️ 순수도 낮음 |
| ISC / 리노공업 | 095340.KQ / 058470.KQ | 24억 / 32억 달러 | 테스트 소켓 | 높음 | ❌ 병목 아님 |

### 4.2 밸류에이션 점검 (필수)

| 회사 | 시총(현지 통화) | 연매출 | PSR | PER | 매출 증가율 | 신호등 |
|---|---|---|---|---|---|---|
| Nitto Boseki | 5,552억 엔 | 1,182억 엔(FY3/26), 1,370억 엔(FY3/27 회사 예상) | 4.7x / 예상 4.1x | TTM 13.3x (특별이익 포함), **예상 순이익 170억 엔 기준 32.7x** | +8.4%, 예상 +15.9% | 🟢 PSR. 다만 TTM PER은 고정자산 매각이익 탓에 착시 |
| Micronics Japan | 4,804억 엔 | 702억 엔(FY12/25), 상반기 457억 엔(회사 수정 예상) | 6.8x / 상반기 연환산 약 5.3x | 25.6x | +26.1%(2025) | 🟢 |
| FormFactor | 76.1억 달러(API) / 68.4억 달러(검산) | 2026년 1~3분기 합계 7.65억 달러 → 연환산 약 10.2억 달러(추정) | 약 6.7~7.5x | 44.7x | 3Q 전년 대비 증가율 데이터 부족, 전분기 대비 +8.6% | 🟡 PER은 높지만 80x 미만 |
| AXT | 40.0억 달러 | 3Q26 7,340만 달러 → 연환산 2.94억 달러 | 연환산 13.6x | 적자(TTM PER 2,033x, 의미 없음) | +162% YoY | 🟡 적자. PSR 15x 근접. 2026년 4월 6.3억 달러 증자 |
| 대만유리 | 1,812억 대만달러 | 415억 대만달러(2025) | 4.4x | 72.0x | -2.4%(2025), 흑자 전환 중 | 🟡 |
| Baotek | 165억 대만달러 | 22.8억 대만달러(2025) | 7.2x | 46.3x | +15.7% | 🟡 데이터 부족 |
| ASMPT | 474.7억 홍콩달러 | 137.4억 홍콩달러(2025) | 3.5x | 30.1x | +10.0% | 🟢 PSR, 순수도 낮음 |
| 한미반도체 | 18.68조원 | 5,767억원(2025) | **32.4x** | 84.5x | +3.2% | 🔴 **PSR >30x이고 증가율 <100%** |
| Technoprobe | 170.3억 유로 | 6.28억 유로(2025), 10.5~11억 유로(2026 가이던스) | 27.1x / 가이던스 기준 15.8x | 83.1x | 상반기 +42.4% | 🟡 PER >80x, 시총 >100억 달러 |
| Ibiden | 5.59조 엔 | 4,162억 엔 | 13.4x | 84.7x | +12.7% | 🟡 PER >80x |
| Kinsus | 5,053억 대만달러 | 393.5억 대만달러 | 12.8x | 166.7x | +28.9% | 🟡 PEG 과도 |

> 시총 검산: 대부분 종목에서 API 시총과 "주가 × 발행주식수"의 편차가 4~16%였다(주식수 갱신 시점 차이로 추정). FormFactor는 두 값을 모두 표기했다. 한국 종목은 네이버 시총으로 역산한 주식수가 야후와 일치했다(편차 <1%).

### 4.3 10년 안전마진 검증

조건: 현재 시총에 매수하고, 10년 뒤 PER 25배에 매도한다. 연 10%를 내려면 10년 뒤 순이익이 **현재 시총의 약 10.4%**여야 한다.

| 회사 | 10년 뒤 필요 순이익 | 현재 순이익(정상화 기준) | 필요 배수 | 낙관 시나리오 가정 | 연수익률 | 판단 |
|---|---|---|---|---|---|---|
| Nitto Boseki | 576억 엔 | 170억 엔(FY3/27 회사 예상) | 3.4배 | T-glass 3배 증설 완수, 순이익 700억 엔 | 약 12.2% | 안전마진 얇음(있음) |
| Micronics Japan | 498억 엔 | 약 188억 엔(TTM) | 2.7배 | HBM 세대 전환 지속, 순이익 600억 엔 | 약 12.1% | 안전마진 얇음(있음) |
| FormFactor | 7.9억 달러 | 약 1.7억 달러(TTM) | 4.6배 | 매출 연 15% 성장, 순이익률 18% → 7.2억 달러 | 약 9.0% | **없음(경계)** |
| AXT | 4.1억 달러 | 적자 | — | 매출 10억 달러, 순이익률 25% | 약 4.6% | **없음** |
| ASMPT | 49.2억 홍콩달러 | 약 15.8억 홍콩달러 | 3.1배 | 순이익 35억 홍콩달러 | 약 6.3% | **없음** |
| 대만유리 | 188억 대만달러 | 약 25억 대만달러 | 7.5배 | 순이익 80억 대만달러 | 약 1.0% | **없음** |
| Baotek | 17.1억 대만달러 | 약 3.6억 대만달러 | 4.8배 | 순이익 10억 대만달러 | 약 4.3% | **없음** |
| 한미반도체 | 1.94조원 | 약 2,211억원 | 8.8배 | 순이익 8,000억원 | 약 0.7% | **없음** |
| Technoprobe | 17.7억 유로 | 약 2.0억 유로 | 8.6배 | 순이익 8억 유로 | 약 1.6% | **없음** |

※ 낙관 시나리오 순이익은 전부 **추정**이다. 회사 가이던스가 아니다.

---

## 5단계: 교차 검증

| 검증 | Nitto Boseki | Micronics Japan | FormFactor | AXT |
|---|---|---|---|---|
| 고객 검증 | ✅ AI 서버·패키지 기판 수요가 FY3/26 실적에 기여(회사 결산) | ✅ 메모리 프로브카드 분기 최대(회사 자료, 2026.5) | ✅ HBM이 전분기 대비 성장 견인(SEC 8-K) | ✅ Lumentum 6년 생산능력 예약, 4,350만 달러 선수금(SEC 8-K) |
| 매출 검증 | ✅ 영업이익 +26.6%, FY3/27 1분기 +84.8% | ✅ 2분기 매출 282.6억 엔, 영업이익 99.1억 엔(이익률 35%) | ✅ 3분기 연속 최대 매출 | ✅ +162% YoY |
| 가격 검증 | ⚠️ 가격 인상 종료 선언 | 데이터 부족 | 데이터 부족 | 데이터 부족 |
| 생산능력 검증 | ✅ 풀가동, 신공장 2027 | ✅ DRAM용 생산능력 확대가 실적 동인 | ✅ 공장 가동 준비비 710만 달러 | ⚠️ 수율 15~20%, 수출허가 |
| 자본 검증 | ✅ 150억 엔 후쿠시마 증설 | ✅ FY2026 capex 190억 엔 계획 | ✅ | ⚠️ 증자로 조달(희석) |

### 5.2 역방향 검증 (멍거식)

**Nitto Boseki**
- 똑똑한 사람들은 왜 안 사나? 2026년 5월 고점 6,580엔에서 57% 하락했다. 이유는 ① FY3/26 FCF -32억 엔 ② 8월 실적에서 추가 증설 발표 부재(하루 -16.9%) ③ 점유율 하락 논쟁(40% 설 vs 90% 설)이다.
- 우회 경로: 대만유리 저CTE 인증 완료, Asahi Kasei Q-glass(CTE 0.5ppm), 장기적으로 유리코어 기판.
- 관점: 독점 공급사가 가격 인상을 멈추고 증설 속도도 경쟁사에 밀리면 **"병목 프리미엄"이 "점유율 방어 비용"으로 바뀌는** 전형적 경로다. 반대로 예상 PER 33배·PSR 4배는 독점 지위를 잃어 가는 기업치고는 싸지 않다. 판단의 축은 11/5 실적의 증설 발표 여부다.

**Micronics Japan**
- 리스크: 메모리 3사 capex에 매출이 집중된다(고객 집중). 2026년 1분기 수주는 전분기보다 줄었다(회사 자료). 메모리 사이클이 꺾이면 프로브카드는 소모품이라도 신규 설계 수요가 급감한다.
- 데이터 상충: FY2026 매출 예상이 출처마다 다르다(5월 자료 716억 엔 vs 8월 Quartr 요약 1,038억 엔). 회사 결산단신으로 확인해야 한다.
- 우회: HBM 웨이퍼 테스트를 대신할 경로는 사실상 없다. 다만 FormFactor·Technoprobe와의 점유율 경쟁은 이어진다.

**FormFactor**
- PER 45배에 10년 연수익률 약 9%(낙관). 병목은 진짜지만 가격은 그 사실을 상당 부분 반영했다.

**AXT**
- 생산 거점이 중국(퉁메이)이다. 2025년 2월부터 InP는 주문 건마다 중국 수출허가가 필요하고, 미국 관련 수출규제 유예는 2026년 11월 27일 만료된다(보도). **정책 하나로 매출이 끊길 수 있다.**
- 52주 최저 7.8달러, 최고 143달러. 2026년 4월 6.3억 달러를 증자했다. 심리 주도 성격이 강하다.
- JX Advanced Metals 7~10배 증설, Sumitomo 3배 증설, Vital Materials 신규 진입 → 2028~29년 공급 충격 가능성.

### 5.3 신호 교차

- 산업 검증: 프로브카드 3사(FORM·MJC·Technoprobe)가 동시에 최대 실적·가이던스 상향 → ✅
- 고객 검증: 인텔(기판 부족), 유니마이크론(T-glass·ABF·CCL 부족), SK하이닉스(완판) → ✅
- 제3자: TrendForce·Counterpoint·Prismark 모두 2027년까지 기판·소재 부족을 전망. 다만 수치(10~21%)는 기관마다 다르다 → ✅(정량은 불확실)

---

## 6단계: 병목 기회 대시보드

### 6.1 순위표

| 순위 | 회사 | 코드 | 시총 | 연매출 | PSR | PER | 병목 고리 | 등급 | 점유율 | 매출 증가율 | 신호 강도 | 밸류에이션 판단 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Micronics Japan | 6871.T | 4,804억 엔 | 702억 엔 | 6.8x | 25.6x | HBM 프로브카드 | A | 메모리 프로브카드 상위(정량 데이터 부족) | +26% | ★★★★ | 적정 |
| 2 | Nitto Boseki | 3110.T | 5,552억 엔 | 1,182억 엔 | 4.7x | 32.7x(예상) | T-glass | S | 저CTE 약 90%(2026.4, 하락 논쟁 중) | +8%(예상 +16%) | ★★★★ | 적정 |
| 3 | FormFactor | FORM | 76억 달러 | 약 10.2억 달러(연환산 추정) | 약 7.5x | 44.7x | HBM 프로브카드 | A | 프로브카드 글로벌 상위 | 3Q 전분기 대비 +8.6% | ★★★ | 다소 높음 |
| 4 | 대만유리 | 1802.TW | 1,812억 대만달러 | 415억 대만달러 | 4.4x | 72.0x | T-glass 2위권 | S | 고급 제품 40~45% 목표(회사 목표) | -2%(흑자 전환 중) | ★★★ | 다소 높음(순수도 낮음) |
| 5 | ASMPT | 0522.HK | 475억 홍콩달러 | 137억 홍콩달러 | 3.5x | 30.1x | TC 본더 | B | SK하이닉스 본딩 물량 10~15%(추정) | +10% | ★★ | 적정이지만 순수도 낮음 |
| 6 | AXT | AXTI | 40억 달러 | 연환산 2.9억 달러 | 13.6x | 적자 | InP 기판 | S | 3개사가 80~90% | +162% | ★★ | ⚠️ 적자, 지정학 리스크 |
| 7 | Baotek | 5340.TWO | 165억 대만달러 | 22.8억 대만달러 | 7.2x | 46.3x | T-glass | S | 데이터 부족 | +16% | ★★ | 데이터 부족 |
| 8 | 한미반도체 | 042700.KS | 18.68조원 | 5,767억원 | 32.4x | 84.5x | TC 본더 | B | 70%+(출처 불확실) | +3% | ★★ | ⚠️ 밸류에이션 선반영 |
| 9 | Technoprobe | TPRO.MI | 170억 유로 | 6.3억 유로 | 27.1x | 83.1x | 프로브카드 | A | 로직 프로브카드 상위 | 상반기 +42% | ★★ | ⚠️ 밸류에이션 선반영 |

### 6.2 한 페이지 요약

```
🎯 Micronics Japan (6871.T) — HBM4 전환의 웨이퍼 테스트 길목을 쥔 메모리 프로브카드 공급사

왜 병목인가:
HBM은 적층 전에 모든 DRAM 다이를 웨이퍼 단계에서 검사해야 하고, 세대가 바뀔 때마다 프로브카드를 새로 설계해야 한다.
메모리 3사가 2029년까지 완판이라 말하며 증설 중이고, 새 라인마다 프로브카드가 필요하다.

왜 이 회사인가:
메모리(특히 DRAM) 비중이 높아 HBM 수요의 순수 노출도가 가장 크다. 2분기 영업이익률 35%는 공급 우위가 이익률로 드러난 신호다.
동종 FormFactor(PER 45)·Technoprobe(PER 83) 대비 PER 26으로 가장 싸다.

촉매 타임라인:
- 단기(1~3개월): 2026년 3분기 결산(11월 예상), 통기 예상 수정 여부
- 중기(3~12개월): SK하이닉스 M15X·용인 1기, 마이크론 HBM4 램프, 2027 메모리 capex 가이던스

주요 리스크:
1. 메모리 capex 사이클이 꺾이면 신규 설계 수요가 급감(고객 집중)
2. FY2026 매출 예상 수치가 출처마다 다름. 결산단신으로 확인 필요

핵심 데이터: 시총 4,804억 엔 / 매출 702억 엔(2025) / PSR 6.8x / PER 25.6x / 증가율 +26% / 병목 사업 비중 추정 90%+
밸류에이션 안전마진 검증: 10년 뒤 필요 순이익 498억 엔(현재 약 2.7배). 낙관 600억 엔 시 연 12.1%. 결론: 안전마진 얇음(있음)
교차 검증 상태: ✅ 고객 검증 / ✅ 매출 검증 / ✅ 밸류에이션 적정 / ❌ 가격 데이터 미검증
결론: 심층 연구 가치 있음
```

```
🎯 Nitto Boseki (3110.T) — AI 패키지 기판 T-glass의 사실상 단독 공급사, 다만 독점이 흔들리는 중

왜 병목인가:
대형 AI 칩 기판은 열팽창으로 휘지 않도록 저CTE 유리섬유 원단이 필수다. 공급은 Nittobo 한 곳에 몰려 있고 신공장은 2027년에야 가동된다.
유니마이크론 회장이 10월에 T-glass·ABF·CCL을 콕 집어 공급 부족으로 꼽았다.

왜 이 회사인가:
S급 병목의 중심에 있는 회사 가운데 유일하게 밸류에이션 관문(PSR 4x)을 통과했다. 고점 대비 57% 떨어지며 기대가 크게 빠졌다.

촉매 타임라인:
- 단기(1~3개월): 11/5 상반기 결산. 추가 증설 발표 여부와 1분기(영업이익 +84.8%)의 지속성
- 중기(3~12개월): 후쿠시마 신공장 가동 준비, 대만유리 저CTE 물량 확대 속도

주요 리스크:
1. 점유율 잠식(대만유리·Asahi Kasei·Taishan). 가격 인상 종료 선언
2. FCF 마이너스(FY3/26 -32억 엔), 증설 자금 부담

핵심 데이터: 시총 5,552억 엔 / 매출 1,182억 엔 / PSR 4.7x / 예상 PER 32.7x(TTM 13.3x는 특별이익 착시) / 예상 증가율 +15.9% / 병목 사업 비중 데이터 부족
밸류에이션 안전마진 검증: 10년 뒤 필요 순이익 576억 엔(FY3/27 예상 대비 3.4배). 낙관 700억 엔 시 연 12.2%. 결론: 안전마진 얇음(있음)
교차 검증 상태: ✅ 고객 검증 / ✅ 매출 검증 / ✅ 밸류에이션 적정 / ⚠️ 독점 지속성 미검증
결론: 심층 연구 가치 있음(11/5 결산 확인 후)
```

### 6.3 행동 제안

| 종목 | 제안 액션 | 이유 |
|---|---|---|
| Micronics Japan | `/investment-team` 심층 리서치 | A급 병목 + 다중 검증 + 동종 대비 최저 PER |
| Nitto Boseki | 11/5 결산 확인 후 `/investment-team` | S급 병목 + 밸류에이션 통과. 독점 약화가 핵심 쟁점 |
| FormFactor | 관찰 목록 | 병목은 진짜, 10년 수익률 경계(약 9%) |
| 대만유리 | 관찰 목록 | T-glass 2위로 Nittobo의 대체 경로. 저CTE 비중 공시 대기 |
| AXT | 관찰 목록(낮은 우선순위) | S급 병목이지만 적자·중국 수출허가·11/27 규제 유예 만료 |
| 한미반도체 | 더 좋은 가격 대기 | PSR 32x 빨간불, 하이브리드 본딩 전환 리스크 |
| ABF 기판 대형주 | 추적 안 함(가격 반영) | Layer 1.5. PER 68~167 |

---

## AI 리서치 편향 점검

- 선두 기업 선호: 소형주를 의도적으로 넣었다(Baotek, AXT). 다만 한국 소형 소재주(유리섬유·CCL)는 이번 스캔에서 데이터가 부족했다 → 다음 스캔 과제.
- 확증 편향: 모든 S급 고리에 해소 신호(TSMC 발언, Nittobo 가격 동결, InP 서류상 생산능력 2배)를 붙였다.
- 시효: 데이터는 대부분 2026년 8~10월 자료다. Nittobo·MJC의 다음 결산은 11월에 나온다.

## 데이터 한계

- MJC FY2026 매출 예상이 출처마다 상충한다(716억 엔 vs 1,038억 엔).
- AXT InP 매출 비중이 출처마다 상충한다(1,360만 달러 vs 3,070만 달러).
- Nittobo T-glass 점유율이 출처마다 상충한다(약 40% vs 약 90%).
- 상당수 정량 수치(공급 격차 %, 리드타임)는 시장조사 기관·블로그 2차 인용이다.
- 시세는 Yahoo Finance 단일 출처이고, 시총 검산 편차가 4~16%다.

---

## 출처

- [SK hynix Q3 2026 (Korea Times)](https://www.koreatimes.co.kr/business/companies/20261028/sk-hynix-logs-record-q3-operating-profit-of-628-bil) · [investinglive](https://investinglive.com/stocks/sk-hynix-q3-operating-profit-beats-at-83tn-won-unveils-100tn-won-shareholder-payout-plan/)
- [TrendForce — Unimicron 30개월 장비 납기 경고(2026-10-20)](https://trendforce.com/news/2026/10/20/news-unimicron-warns-of-ic-substrate-crunch-up-to-30-month-equipment-lead-times-20-material-gap-in-2027)
- [Intel 10-Q 3Q26 (SEC)](https://www.sec.gov/Archives/edgar/data/0000050863/000005086326000191/intc-20260926.htm) · [TrendForce — Intel CEO 공급 부족 발언](https://www.trendforce.com/news/2026/09/16/news-intel-ceo-flags-ai-supply-squeeze-memory-prices-up-5-7x-its-cpus-meet-just-50-of-demand/)
- [Digitimes — T-glass 2028년까지 부족](https://www.digitimes.com/news/a20260814PD224/demand-ic-substrate-2028-fiberglass-cloth-infrastructure.html) · [Tom's Hardware — ABF 기판 2026](https://www.tomshardware.com/tech-industry/semiconductors/the-state-of-abf-substrates-in-data-center-silicon-in-2026-solving-the-supply-crunch-and-material-wall-beneath-every-ai-accelerator) · [BigGo — TSMC CoWoS 격차 축소](https://finance.biggo.com/news/18911103-c55c-4611-b80a-b6d155ed9dbe) · [bestpcbs — Counterpoint ABF 격차](https://www.bestpcbs.com/blog/2026/08/abf-substrate-shortage/)
- [TrendForce — Nittobo 추가 가격 인상 없음](https://www.trendforce.com/news/2026/08/06/news-nittobo-raises-fy2027-net-profit-forecast-by-jpy-3b-no-further-t-glass-price-hikes-planned/) · [CompositesWorld — T-glass](https://www.compositesworld.com/news/on-the-radar-the-role-of-t-glass-in-ai) · [Investing.com — Nittobo 급락](https://in.investing.com/news/stock-market-news/why-is-nitto-boseki-stock-plunging-today-93CH-5538456) · [JPX — Nittobo FY3/26 결산](https://www2.jpx.co.jp/disc/31100/081220260512525575_tse-acedjpsm-31100-20260512331100-ixbrl.htm) · [JPX — Nittobo FY3/27 1Q](https://www2.jpx.co.jp/disc/31100/081220260805509788_tse-qcedjpsm-31100-20260805331100-ixbrl.htm)
- [台玻 T-glass 인증 (uanalyze)](https://uanalyze.com.tw/articles/4544057391) · [Baotek (Global Technology Research)](https://globaltechresearch.substack.com/p/baotek-5340-tt-taiwans-nittobo)
- [FormFactor 3Q26 (SEC 8-K)](https://www.sec.gov/Archives/edgar/data/0001039399/000103939926000040/ex9901-earningsreleasexq326.htm) · [FormFactor 2Q26 (SEC 8-K)](https://www.sec.gov/Archives/edgar/data/0001039399/000103939926000030/ex9901-earningsreleasexq226.htm)
- [Micronics Japan 2026.5 자료](https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260513/20260513529134.pdf) · [Quartr — MJC 2Q26](https://quartr.com/events/micronics-japan-co-ltd-6871-q2-2026_F92QpaaF) · [traders.co.jp — MJC](https://www.traders.co.jp/stocks/61_6871/news/2192517)
- [Technoprobe 상반기 2026 (teleborsa)](https://www.teleborsa.it/AMP/News/2026/08/05/technoprobe-alza-ancora-target-2026-dopo-primo-semestre-in-forte-crescita-209.html) · [Quartr — Technoprobe 2Q26](https://quartr.com/events/technoprobe-s-p-a-tpro-q2-2026_FGoKKbRz)
- [AXT 3Q26 (SEC 8-K)](https://www.sec.gov/Archives/edgar/data/0001051627/000143774926033941/ex_1013304.htm) · [AXT Lumentum 계약 (SEC 8-K)](https://www.sec.gov/Archives/edgar/data/0001051627/000143774926024883/axti20260715_8k.htm) · [Compound Semiconductor — InP](https://compoundsemiconductor.net/article/125737/AI_optics_a_435b_market_waiting_on_InP)
- [TrendForce — 하이브리드 본딩 일정 재검토](https://www.trendforce.com/news/2026/07/07/news-samsung-sk-hynix-reportedly-reconsider-hybrid-bonding-timeline-16-high-hbm4e-may-be-earliest-adoption/) · [Tech Times — 한미반도체 TC 본더](https://www.techtimes.com/articles/329060/20261015/hanmi-semiconductor-cements-tc-bonder-leadership-semicon-west-hbm4-orders-surge.htm) · [MTN — 한미·세메스·한화](https://news.mtn.co.kr/news-detail/2026021317395078451)
- [SOX 8일 연속 하락 (Stocktwits)](https://stocktwits.com/news-articles/Markets/Equity/semiconductor-stocks-sox-losing-streak-2-trillion-ai-selloff/cZxKaOoRBsy) · [cryptobriefing](https://cryptobriefing.com/us-chip-stocks-longest-losing-streak-2008/)
- 시세·재무: `tools/global_stock_data.py`(Yahoo Finance, 한국 종목은 네이버 시총 교차)

## 실행 정보

- 작성일: 2026-10-31
- 스킬: /bottleneck-hunter (전체 스캔, 트렌드 "반도체 수요에 따른 병목")
- 데이터 시점: 시세 2026-10-31 조회(직전 거래일 종가 추정), 실적은 2026-10-29까지 공개분
- 출처: Yahoo Finance·네이버(시세/재무), SEC EDGAR, JPX 공시, TrendForce, Digitimes 외 위 목록
