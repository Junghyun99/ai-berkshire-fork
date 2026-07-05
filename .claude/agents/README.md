# .claude/agents — 에이전트 팀 정의

이 디렉토리는 팀 기반 Skill(`investment-team`, `earnings-team`, `news-pulse`,
`private-company-research`)이 실제로 멀티 에이전트로 구동되도록 하는 **서브에이전트
정의 파일**을 담는다. Claude Code가 이 저장소에서 실행되면 여기의 `*.md`가
자동으로 로드되어 `Agent` 툴의 `subagent_type`으로 사용 가능해진다.

## 구동 모델 (중요)

이 하네스에는 `TeamCreate`/`SendMessage` 같은 peer-to-peer 팀 도구가 **없다**.
대신 **오케스트레이터(메인 세션 = team-lead) + 서브에이전트** 허브-스포크 구조를 쓴다:

1. team-lead(메인 세션)가 **한 메시지에서 `Agent` 툴을 N번 호출** → N개 서브에이전트 병렬 실행.
2. 각 서브에이전트는 분석을 마치면 **최종 메시지(보고서)를 툴 결과로 반환**한다.
   (별도 메시지 통신이나 shutdown 절차 없음)
3. team-lead가 반환된 보고서들을 종합해 최종 보고서·파일을 작성한다.

에이전트 파일 = **지속적 페르소나 + 분석 프레임 + 데이터 규율**.
구체적 과제(어느 회사/어느 분기)는 Skill이 실행 시 `Agent`의 `prompt`로 주입한다.

## 역할 목록

| 에이전트 | 관점/포지션 | 사용 Skill |
|---------|-----------|-----------|
| business-analyst | 돤융핑 · 비즈니스 모델 | investment-team, earnings-team |
| financial-analyst | 버핏 · 재무 밸류에이션 | investment-team, earnings-team |
| industry-researcher | 멍거 · 산업 경쟁 | investment-team, earnings-team |
| risk-assessor | 리루 · 리스크 경영진 | investment-team, earnings-team |
| editor | 발행용 아티클 편집 | earnings-team, wechat-article |
| reader-reviewer | 일반 투자자 독자 심사 | earnings-team, wechat-article |
| company-event-scout | 기업 이벤트 정찰 | news-pulse |
| regulatory-watcher | 규제·정책 정찰 | news-pulse |
| industry-peer-analyst | 산업·경쟁사 정찰 | news-pulse |
| sentiment-tracker | 시장 심리 정찰 | news-pulse |
| business-decoder | 비상장 비즈니스 모델 분해 | private-company-research |
| financial-detective | 비상장 재무 짜맞추기·밸류에이션 | private-company-research |
| competitive-mapper | 비상장 산업 구도 | private-company-research |
| risk-governance-analyst | 비상장 리스크·지배구조 | private-company-research |
| tech-ip-analyst | 비상장 기술·지식재산 | private-company-research |
| signal-miner | 비상장 대체 데이터 신호 | private-company-research |

## 프론트매터 규약

```yaml
---
name: <subagent_type로 쓰일 이름>
description: 언제 이 에이전트를 쓰는지 (team-lead가 라우팅에 참고)
tools: WebSearch, WebFetch, Bash, Read, Write, Grep, Glob   # 생략 시 전체 상속
model: sonnet                                               # 필요 시 opus로 상향
---
<시스템 프롬프트: 페르소나 + 분석 프레임 + 데이터 규율 + 출력 규격>
```

## 환경 요건

- 한국 주식 리서치 시 `DART_API_KEY` 환경변수 필요(`tools/dart_data.py`).
- `tools/*.py`는 표준 라이브러리만 사용 — 별도 `pip install` 불필요.
- 서브에이전트가 WebSearch/WebFetch로 데이터를 수집하므로 아웃바운드 네트워크 필요.

## 폴백

`Agent` 툴 병렬 실행이 세션 한도 등으로 실패하면, team-lead가 각 역할을
**순차 수행**하고 결과 파일을 직접 작성한다. 산출물 구조는 동일하게 유지한다.
