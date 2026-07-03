#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

mkdir -p "$DEST"

for skill_dir in "$ROOT"/skills/*/; do
  name="$(basename "$skill_dir")"
  mkdir -p "$DEST/$name"
  cp -R "$skill_dir." "$DEST/$name/"
done

chmod +x "$ROOT"/tools/*.py "$ROOT"/tools/*.sh 2>/dev/null || true

echo "Installed Claude Code skills to $DEST"

# 과거 ~/.claude/commands/ 방식으로 설치된 구버전 복사본이 남아 있으면 안내
OLD_DEST="$HOME/.claude/commands"
leftovers=()
for skill_dir in "$ROOT"/skills/*/; do
  name="$(basename "$skill_dir")"
  [ -f "$OLD_DEST/$name.md" ] && leftovers+=("$OLD_DEST/$name.md")
done
if [ "${#leftovers[@]}" -gt 0 ]; then
  echo ""
  echo "주의: 구버전 커맨드 복사본이 남아 있습니다 (skill과 이름이 겹치므로 삭제를 권장):"
  printf '  %s\n' "${leftovers[@]}"
fi
