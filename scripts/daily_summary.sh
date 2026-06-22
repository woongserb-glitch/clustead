#!/usr/bin/env bash
# Clustead 일일 요약 — 매일 09:00(KST) cron 권장.
#
# server_health_check.sh 가 '상태 변화 시'에만 알리는 것과 달리, 이 스크립트는
# 하루 1회 '전날' 집계를 보고한다. CDN 캐시 도입 후 healthz HTTP 000(워커 포화)
# 빈도가 실제로 줄었는지 추세를 보기 위함. 웹훅 설정은 server_health_check 과 공유.
#
# 설치(서버):
#   chmod +x /root/clustead/scripts/daily_summary.sh
#   ( crontab -l 2>/dev/null; echo "0 9 * * * /root/clustead/scripts/daily_summary.sh" ) | crontab -
set -u

CONFIG=/etc/clustead-monitor.env
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && . "$CONFIG"

WEBHOOK="${CLUSTEAD_ALERT_WEBHOOK:-}"
LOG="${CLUSTEAD_MONITOR_LOG:-/var/log/clustead-monitor.log}"
CONTAINER="${CLUSTEAD_CONTAINER:-clustead-app-1}"

y=$(date -d 'yesterday' '+%F')
fails=$(grep "^$y" "$LOG" 2>/dev/null | grep -c 'FAIL')
checks=$(grep "^$y" "$LOG" 2>/dev/null | grep -cE '\[(OK|FAIL)\]')
wt=$(docker logs --since 24h "$CONTAINER" 2>&1 | grep -c 'WORKER TIMEOUT')

msg="📊 [Clustead] 일일 요약 ${y} — healthz FAIL ${fails}/${checks}회, 워커타임아웃(24h) ${wt}건"

ts=$(date '+%F %T')
echo "${ts} ${msg}" >> "$LOG"

if [ -n "$WEBHOOK" ]; then
  # Slack("text") / Discord("content") 양쪽 키 호환.
  payload=$(printf '{"text":%s,"content":%s}' "\"$msg\"" "\"$msg\"")
  curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$WEBHOOK" >/dev/null 2>&1
fi
exit 0
