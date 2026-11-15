# SPY·IEF 발행사 분배 기록 대조 — 2026-11-15

## 결론

기존 Yahoo 원본과 현재 발행사 기록의 분배락일은 SPY 92건, IEF 272건 모두 일치했다. 주당 금액의 절대 차이를 0.0005 USD 이하로 허용하면 SPY 91건, IEF 272건이 범위 안이다. SPY 2021-12-17은 Yahoo 1.633 USD, State Street 1.636431 USD로 0.003431 USD 차이가 난다. 해당 행의 단기·장기 자본이득은 모두 0이다. 차이의 원인과 수정주가 반영 여부는 미확인이다.

이번 결과는 분배 기록의 부분 교차검증이다. 발행사 자료도 지금 내려받은 기록이므로 과거 최초 공개 시각·수정 이력을 입증하지 않는다. 시장 종가 및 조정종가의 전수 인증, 과거 빈티지 확인은 미완료다. #53·#54를 종료하지 않으며 research_proxy를 유지한다.

## 자료와 방법

- 비교 기간: 기존 원본의 거래일 2004-01-02~2026-09-30. SPY 발행사 분배 이력은 1993-03-19부터, IEF는 2002-09-03부터 제공된다. 원본 범위 밖의 기록은 비교에서 제외했다.
- Yahoo: 2026-10-29 시장 스냅샷 ZIP의 raw/yahoo/SPY.json 및 IEF.json. 기존 manifest SHA-256과 일치해야 실행한다. JSON 이벤트의 timestamp를 America/New_York로 변환해 분배락일을 맞춘다.
- [State Street SPY 상품 페이지](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy)의 Historical Distributions → [분배금 페이지](https://www.ssga.com/us/en/individual/resources/documents/etf-dividend-distributions) → Historical Distributions XLSX. DIVIDEND + SHORT TERM CAPITAL GAIN + LONG TERM CAPITAL GAIN을 합산한다.
- [iShares IEF 상품 페이지](https://www.ishares.com/us/products/239456/IEF)의 Data Download Excel. Distributions 시트의 Ex-Date와 Total Distribution을 사용한다.
- 실제 내려받은 파일 URL과 SHA-256은 results.json에 기록했다. 원본은 재배포 권한이 확인되지 않아 GitHub에 넣지 않는다.
- Decimal 십진 연산으로 비교한다. 0.0005 USD는 소수 셋째 자리 반올림과 양립 가능한지 확인하는 허용오차이며, 제공사의 반올림 방식이나 자료 정확성을 인증하는 기준은 아니다. 완전 일치 건수와 허용오차 내 건수를 구분한다.
- IEF 원본 XML에 이스케이프되지 않은 URL의 & 6개가 있어 파싱용 메모리에서만 &amp;로 처리했다. 원본 바이트와 해시는 보존한다. 중복 분배락일은 오류로 처리한다.

| 항목 | SPY | IEF |
| --- | ---: | ---: |
| 기존/발행사 분배 건수 | 92 / 92 | 272 / 272 |
| 날짜 일치 | 92 | 272 |
| 금액 완전 일치 | 1 | 2 |
| 금액 차이 ≤ 0.0005 USD | 91 | 272 |
| 허용오차 밖 | 1 | 0 |
| 최대 절대 차이 USD | 0.003431 | 0.000500 |
| 한쪽에만 존재하는 날짜 | 0 | 0 |

## 가격과 과거 가용성의 미결

IEF Historical 시트에는 2002-07-22~2026-11-13의 6,122개 행이 있으나 가격 필드는 NAV per Share다. NAV와 거래소 종가는 다른 관측값이므로 기존 Yahoo 종가와 같아야 한다는 검사를 수행하지 않았다. SPY Product Data의 관측일은 2026-11-12로 기존 스냅샷 끝 이후다. 따라서 이 자료만으로 과거 시장 종가를 검증할 수 없다.

기존 엔진은 Yahoo adjclose 수익률을 사용한다. events.dividends의 한 건 차이가 adjclose에도 그대로 반영됐는지는 별도 확인이 필요하다. 분배금만 바꿔 기존 수익률에 덧붙이면 중복 반영될 수 있으므로 입력과 성과를 변경하지 않았다. 이번 작업에서는 CAGR·MDD·Sharpe·Sortino를 재계산하지 않았다.

현재 파일의 과거 행, record date, payable date를 당시 데이터베이스에서 접근 가능했다는 증거로 취급하지 않는다. 개별 공시의 최초 공개본 또는 시점별 보관 자료가 추가로 필요하다. 이 대조로 실운용 성과나 과거 시점 통제가 검증된 것은 아니다.

다음은 SPY 해당 분배금의 당시 공시 및 수정주가 조정계수 확인이다. 이후 독립 시장 종가 자료를 확보하면 공식 분배금 재투자 수익률과 기존 조정종가 수익률의 민감도를 비교할 수 있다. 공식 NAV 기반 수익률 비교는 별도의 정의를 가진 보조 실험으로 기록해야 한다.

## 재현과 검증

Python 3 표준 라이브러리만 사용한다. 원본 파일명이 raw/spy-distributions.xlsx, raw/spy-product.xlsx, raw/ief-download일 때:

```bash
python3 check.py --raw raw --yahoo /path/to/snapshot-20261029/raw/yahoo --output results.json
python3 -m unittest discover -s . -p test_check.py -v
```

현재 URL 재다운로드는 파일 갱신으로 다른 해시가 나올 수 있다. 같은 결과의 정확 재현에는 results.json에 기록된 해시의 보존본이 필요하다. 원본 Yahoo 해시가 다르면 실행을 차단한다.

실행 결과: 실제 파일 대조 exit 0, 합성 회귀 테스트 4개 통과. 테스트는 허용오차 경계·양방향 날짜 누락·차이 보존·중복 차단·XML 희소 셀과 원본 불변을 확인한다. 저장소 전체 테스트는 이번 연구 스크립트 변경에서 재실행하지 않았다. financial_rigor.py calc도 실행했지만 그 출력은 이진 부동소수점 잔차를 포함하므로 표의 정확 차이는 Decimal 결과를 따른다. report_audit.py extract --dry-run은 형식상 표본 추출일 뿐 독립 수치 인증이 아니다.

## 실행 정보

- 작성·실자료 수집일: 2026-11-15 UTC.
- 실행: Codex/Work, Python 3; 별도 투자정책 Skill 실행 없음.
- 원본 및 산출물: check.py, test_check.py, results.json, 본 보고서.
- 데이터 시점: 기존 입력 2026-09-30까지, 현재 발행사 자료의 관측 범위는 위에 별도 표시.
- 정책: IPS v0.4 DRAFT 유지. 투자기법·데이터 품질 연구이며 실제 주문·계좌 관리는 수행하지 않았다.
