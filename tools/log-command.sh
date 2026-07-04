#!/bin/bash
# 사용자 지침을 로그 파일에 기록합니다.
# 의존하다 user_prompt_submit hook 부르다，stdin 사용자 입력을 받습니다

LOG_DIR="$HOME/ai-berkshire/logs"
LOG_FILE="$LOG_DIR/command-log.jsonl"
COUNTER_FILE="$LOG_DIR/.counter"

mkdir -p "$LOG_DIR"

# 사용자 입력 읽기
PROMPT=$(cat)

# 빈 입력 건너뛰기
[ -z "$PROMPT" ] && exit 0

# 타임스탬프는 초 단위로 정확합니다.
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 차단하기 전에200문자를 레코드로 사용(지나치게 긴 입력 방지)）
PROMPT_SHORT=$(echo "$PROMPT" | head -c 200 | tr '\n' ' ' | tr '"' "'")

# 로그에 추가（JSONL체재）
echo "{\"time\":\"$TIMESTAMP\",\"prompt\":\"$PROMPT_SHORT\"}" >> "$LOG_FILE"

# 계수기
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE")
else
    COUNT=0
fi
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

# 모든10출력 알림（hook stdout 에게 표시됩니다 Claude）
if [ $((COUNT % 10)) -eq 0 ]; then
    TOTAL=$(wc -l < "$LOG_FILE" | tr -d ' ')
    echo "[명령 로그] 누적된 기록 ${TOTAL} 지침. 달리는 것이 좋습니다 /command-log 최근 지침에 대한 보충 배경 요약。"
fi
