# AI Berkshire Agent Guide

This repository contains investment research workflows, reports, and shared
validation tools, maintained for Claude Code. (This fork removed the upstream
Codex compatibility layer — `codex-skills/`, `codex-prompts/`, and their sync
scripts. See the upstream repo if you need Codex support.)

## Project Layout

- `.claude/skills/<name>/SKILL.md`: Claude Code project skills (canonical
  workflows), loaded automatically when Claude Code runs in this repository.
- `tools/*.py`: shared financial validation and data tools.
- `reports/`: research outputs. Do not rewrite unrelated reports while changing
  tooling or skills.
- `스크리닝/`: archived screening results (upstream author's output).
- `실전기록/`: trading log kept for reference (upstream author's records).

## Compatibility Rules

- Treat `.claude/skills/<name>/SKILL.md` as the canonical workflow source.
- Keep tool paths compatible with the documented checkout path:
  `~/ai-berkshire/tools/...`
- Keep `CLAUDE.md` as the primary behavior guide; this `AGENTS.md` is a
  secondary guide for other agent tools.

## Research Quality Rules

- Financial data must come from at least two independent sources when the skill
  requires verification.
- Use exact arithmetic tools for market cap, valuation, cross-source checks, and
  scenario analysis:
  `python3 tools/financial_rigor.py ...`
- Use report audit tooling before treating generated research as publishable:
  `python3 tools/report_audit.py ...`
- Clearly label low-confidence conclusions, incomplete data, and source gaps.
- This project is for learning and research, not investment advice.

## Editing Rules

- Preserve existing report files unless the task specifically asks to change
  them.
- Keep changes scoped to the requested skill, tool, script, or documentation.
- Write new reports in Korean, following the naming rules in `CLAUDE.md`.


## ChatGPT Work Handoff (2026-10-29)

Before modifying this repository from Work or another agent runtime, read:
1. `CLAUDE.md` and this file (existing instructions remain in force).
2. `docs/PROJECT_STATUS.md` for current PR dependencies, known incomplete tests, and source of truth.
3. `docs/DECISIONS.md` for **user-confirmed** portfolio scope vs pending choices.
4. `docs/ROADMAP.md` for the research/development sequence.
5. `docs/DATA_SOURCES.md` for data provenance, live-download status, and return/FX quality rules.
6. `reports/policies/ai-berkshire-primary/draft-v0.4-2026-10-28.md` for latest **DRAFT, NOT ACTIVE** investment policy.

**Mandatory safety boundaries:** PR merge does not equal investment-policy approval; policy validators and the local registry are incomplete MVPs. Never infer successful tests from committed test files. Never invent actual financial data, backtest results, active policies, broker actions, or authenticated human approvals.

**Stacked research PRs:** #37 → #38 → #39. Verify each current PR state in GitHub before merging, retargeting, or editing. Use one PR per coherent change and include exact test results, citations, as-of timestamps, and unresolved limitations. Preserve existing `.claude/skills`, report labels, and Python interfaces.
