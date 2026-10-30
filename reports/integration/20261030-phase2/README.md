# Phase 2 연구 변경의 main 통합 검증

2026-10-30 KST. 추적 이슈 #49, 미결 목록 #57.

## 변경과 판단

main `85403609398c220cf1c2a013020e5b97376d470d`와 #48 누적 연구 head `3d6e741c48ee87b2b9edbb4c91e3bce025e3022e`를 통합했다. 충돌은 `docs/PROJECT_STATUS.md` 한 파일이며 main의 기존 137개 테스트 기록과 #42~48 연구 기록을 모두 보존했다. `saa_data_quality.py`와 `test_decision_ledger.py`의 #41 파일 종료 수정은 main 내용과 바이트 단위로 일치한다. 정책과 canonical Skills는 바꾸지 않았다.

검증한 코드 커밋은 `fdff24dc873d9a6f4f5ca2d42c24b6abd8b84d36`, 트리는 `8636ce1651a112b75c5dd6f037c80b7e06f9050a`다. 로컬 테스트 트리와 GitHub 생성 트리가 같다. 그 뒤 추가한 이 보고서·증거 JSON·상태 갱신은 문서 변경이다.

#42 초기 결함이 있는 상태만 main에 반영하는 대신 #42→#43→#44→#45→#46→#47→#48을 조상으로 보존한 최종 상태를 통합 PR로 검토한다. 이는 연구 코드 통합 판단이며 공식 데이터 검증 완료나 투자정책 승인이 아니다. #42 Draft를 데이터 인증 완료로 전환하지 않는다. 통합 PR 병합 후 기존 PR의 실제 종료/병합 상태와 commit ancestry를 다시 확인한다.

## 실행 검증

- Python 3.12.14 / NumPy 2.3.5 / Pandas 2.2.3 / xlrd 2.0.1 / pdftotext를 사용하는 기존 Work 환경.
- `python3 -W always::ResourceWarning -m unittest discover -s tools/tests -v`: **180 tests, OK, 0.184초, ResourceWarning 0건**.
- 초기 스냅샷의 복사본으로 `saa_real_experiment.py` 실행: 예상대로 `BLOCKED_SOURCE_RECONCILIATION: 069500.KS,148070.KS`, 성과 출력 없음. 원본 스냅샷은 수정하지 않았다.
- 같은 원본 복사본과 보완 스냅샷으로 `saa_rebuilt_experiment.py` 실행: 120개 독립 지표 대조 통과, 보고된 결과 JSON과 해시 일치.
- 새 재구성 입력으로 `saa_matched_universes.py`: 120개 독립 지표 대조, 기존 결과 해시 일치.
- 같은 입력으로 `saa_defensive_mix.py`: 360개 독립 지표 대조, 기존 결과 해시 일치.
- 새 방어자산 결과를 기준으로 `saa_defense_uncertainty.py`: 기본 성과 24개 독립 대조 및 재표본화 결과 해시 일치.
- 자세한 결과/기존 파일 해시는 [verification.json](verification.json)에 있다. 같은 지표의 반복 검증을 독립 증거 개수로 합산하지 않는다.

초기 차단 명령의 실패는 의도한 성공 조건이며 통합 테스트 실패가 아니다. 재현 과정은 개인 원본의 복사본과 별도 출력 디렉터리를 사용했다. 새 원시 자료나 합성 시장 가격을 추가하지 않았다.

통합 트리에 `.github` workflow가 없고 #48 head의 GitHub check-runs는 0개였다. 따라서 위 결과는 로컬 통합 검증이며 원격 CI 통과라고 표현하지 않는다. API workflow 목록 조회는 성공하지 않아 이를 원격 CI 설정 전체의 인증으로 확대하지 않는다.

## 미해결 항목

#50 정책 게이트, #51 승인/등록, #52 Skill 종단간, #53 공식 장기 자료, #54 빈티지, #55 평가 기준/미사용 구간, #56 사용자 정책 선택은 여전히 별도 미완료다. #49 코드 통합의 성공은 이 항목들을 닫지 않는다. `research_proxy`, 초기 성과 보존용 표기, source gate를 유지한다. IPS v0.4 DRAFT, 실제 주문 없음.

## 재현 명령 구조

기존 재현 ZIP의 원본을 작업용 복사본 `ORIGINAL_COPY`로 준비한다. `SUPPLEMENT`는 보완 원본, `NEW`는 존재하지 않는 새 실험 출력이다.

```bash
python3 -W always::ResourceWarning -m unittest discover -s tools/tests -v
python3 tools/saa_real_experiment.py --root ORIGINAL_COPY --output BLOCKED_OUTPUT
# 위 명령은 현재 원자료에서 차단되어야 한다.
python3 tools/saa_rebuilt_experiment.py --original ORIGINAL_COPY --supplement SUPPLEMENT --output NEW
python3 tools/saa_matched_universes.py --inputs NEW/inputs --qa NEW/inputs/qa.json --output MATCHED.json
python3 tools/saa_defensive_mix.py --inputs NEW/inputs --qa NEW/inputs/qa.json --output DEFENSE.json
python3 tools/saa_defense_uncertainty.py --inputs NEW/inputs --qa NEW/inputs/qa.json --baseline DEFENSE.json --output UNCERTAINTY.json
```

문서 작성 후 상대 링크·충돌 표식·`git diff --check`를 확인한다. 보고서 감사는 사실 추출 보조이며 출처 인증이 아니다.
