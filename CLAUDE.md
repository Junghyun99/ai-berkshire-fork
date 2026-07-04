# AI Berkshire — 프로젝트 지침

## 프로젝트 개요

Claude Code 기반의 가치투자 리서치 Skill 모음집. 4대 거장 프레임워크: 버핏, 멍거, 돤융핑, 리루.
원본: xbtlin/ai-berkshire → 포크: Junghyun99/ai-berkshire-fork (한국어화 버전)

## 프로젝트 구조

```
.claude/skills/  — 투자 리서치 Skill 정의({이름}/SKILL.md), 프로젝트 스킬로 자동 로드
tools/           — 보조 도구 (financial_rigor.py 정밀 계산, global_stock_data.py 한국·미국·홍콩 시세/재무 수집, ashare_data.py 중국 A주 전용)
reports/         — 투자 리서치 보고서 출력
assets/          — 이미지 등 정적 리소스
```

## 보고서 디렉토리 구조

모든 보고서는 **회사명**으로 폴더를 만들고, 회사 관련 보고서는 모두 해당 폴더에 넣는다:

```
reports/
├── AI산업연구/               — AI 밸류체인 전경 연구 (상단 고정)
│   ├── AI5층케이크-산업전경연구-20260605.md
│   └── AI5층케이크-아티클-20260605.md
├── 텐센트/                   — 텐센트의 모든 리서치 보고서
│   ├── 텐센트-research-20260408.md
│   ├── 텐센트-earnings-2025Q4.md
│   ├── 텐센트-management-20260409.md
│   └── 텐센트-thesis.md
├── 삼성전자/                 — 삼성전자의 모든 리서치 보고서
├── 원전-industry-20260409.md — 산업 보고서는 루트에
├── AI컴퓨팅-funnel-20260509.md — 퍼널 스크리닝 보고서는 루트에
├── AI-로테이션판단-20260509.md — 테마 수준 종합 판단 보고서는 루트에
├── portfolio-latest.md        — 포트폴리오 보고서는 루트에 (지속 갱신)
└── 다중회사비교-checklist-20260408.md — 다중 회사 보고서는 루트에
```

참고: 기존 reports/ 안의 중국어 폴더·파일명은 원저자(업스트림)의 산출물이다. 새 보고서는 위의 한국어 규칙을 따른다.

## 보고서 명명 규칙

| Skill | 파일 명명 형식 | 예시 |
|------|---------|------|
| /investment-team | `{회사명}/` 디렉토리에 4개 관점 + 최종 보고서 | `reports/삼성전자/최종보고서.md` |
| /investment-research | `{회사명}-research-{YYYYMMDD}.md` | `reports/텐센트/텐센트-research-20260408.md` |
| /investment-checklist | `{회사명}-checklist-{YYYYMMDD}.md` | `reports/텐센트/텐센트-checklist-20260408.md` |
| /industry-research | `{산업명}-industry-{YYYYMMDD}.md` (루트) | `reports/원전-industry-20260409.md` |
| /industry-funnel | `{산업명}-funnel-{YYYYMMDD}.md` (루트) | `reports/AI컴퓨팅-funnel-20260509.md` |
| /private-company-research | `{회사명}-private-{YYYYMMDD}.md` | `reports/바이트댄스/바이트댄스-private-20260408.md` |
| /earnings-review | `{회사명}-earnings-{기간}.md` | `reports/텐센트/텐센트-earnings-2025Q4.md` |
| /earnings-team | `{회사명}/` 디렉토리에 4개 거장 관점 + 연구 초안 + 발행 아티클 + 독자 심사 | `reports/텐센트/텐센트-earnings-2025Q4.md` (발행 확정본) |
| /thesis-tracker | `{회사명}-thesis.md` (장기 유지관리) | `reports/텐센트/텐센트-thesis.md` |
| /portfolio-review | `portfolio-latest.md` (루트, 지속 갱신) | `reports/portfolio-latest.md` |
| /management-deep-dive | `{회사명}-management-{YYYYMMDD}.md` | `reports/텐센트/텐센트-management-20260409.md` |

## /investment-team 파일 구조

```
reports/{회사명}/
├── README.md                          — 리서치 프레임 개요 + 핵심 결론
├── 01-비즈니스모델분석-돤융핑관점.md
├── 02-재무밸류에이션분석-버핏관점.md
├── 03-산업경쟁분석-멍거관점.md
├── 04-리스크경영진평가-리루관점.md
└── 최종보고서.md                      — Team Lead 종합 보고서
```

## 투자 분석 핵심 원칙 (최고 우선순위)

- **객관, 객관, 객관** — 모든 투자 분석은 사실과 데이터에 기반해야 하며, 주관적 억측 엄금
- "사실"과 "관점"을 엄격히 구분: 사실은 데이터로 뒷받침하고, 관점은 반드시 "관점" 또는 "추측"으로 명시
- **입장을 미리 정하지 않는다**: 강세도 약세도 전제하지 않는다. 데이터 먼저, 논리 전개, 마지막에 결론. 결론은 데이터에서 자연스럽게 도출되어야 한다
- "내 생각에는", "느낌상", "명백히" 같은 주관적 표현 금지. "데이터에 따르면", "증거가 보여주듯", "XX 출처에 따르면"으로 대체
- **양면 제시**: 모든 핵심 판단에 반대 논거("그러나 다른 한편으로...")를 붙여 독자가 스스로 저울질하게 한다
- 불확실한 것은 정직하게 "불확실" 또는 "데이터 부족"이라고 말하고, 추측으로 확실성을 채우지 않는다
- 모든 skill(investment-team, investment-research, earnings-review 등)은 실행 시 위 원칙을 준수해야 한다

## 보고서 언어와 스타일

- 모든 보고서는 **한국어** 사용
- 스타일: 직접적이고 예리하게, 군말 없이
- 데이터에는 출처를 표기하고, 핵심 데이터는 최소 2개 출처로 교차 검증
- 추정값에는 반드시 "추정" 명기
- 점수는 ★기호 사용 (★1-5), 반 별 없음
- 버핏/멍거/돤융핑/리루의 어록을 곁들여 코멘트

## GitHub 작업

- 로컬 클론 경로: `~/ai-berkshire/`
- 원격 저장소: `https://github.com/Junghyun99/ai-berkshire-fork.git`
- 푸시 전 먼저 `git pull --rebase origin main` (원격에 새 커밋이 있을 수 있음)
- commit message는 한국어로, 무엇을 바꿨는지 명확하게
- 중간 과정 파일(data_collection.md 등)은 푸시하지 않고 최종 보고서만 푸시

## 자주 쓰는 명령

```bash
# 보고서를 GitHub에 푸시
cd ~/ai-berkshire
git add reports/xxx.md
git commit -m "xxx 보고서 추가"
git pull --rebase origin main
git push origin main
```

## 주의사항

- 시가총액은 반드시 수동 검산: 주가 × 총주식수를 보고서 시총과 대조
- 통화 단위를 명확히 (홍콩달러/위안/달러/원화), 혼동 방지
- PER/ROE 등 지표는 tools/financial_rigor.py 로 정밀 계산
- 보고서 작성 완료 후 GitHub 푸시 여부를 능동적으로 질문
