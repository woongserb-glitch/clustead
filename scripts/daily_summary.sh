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

# 전날의 '점검 라인'만 추린다. 이 로그에는 매일 09:00 요약 라인도 함께 쌓이는데,
# 그 문구에 'FAIL' 이라는 낱말이 들어 있어 예전처럼 grep -c 'FAIL' 로 세면 요약
# 라인까지 +1 로 잘못 잡힌다(2026-07-18 '121/288' 오보의 원인). 반드시 '[FAIL]'
# 대괄호 형태로, 그리고 점검 라인으로 한정해서 센다.
day_checks=$(grep "^$y" "$LOG" 2>/dev/null | grep -E '\[(OK|FAIL)\]')
checks=$(printf '%s' "$day_checks" | grep -cE '\[(OK|FAIL)\]')
fail_lines=$(printf '%s' "$day_checks" | grep '\[FAIL\]')
fails=$(printf '%s' "$fail_lines" | grep -c '\[FAIL\]')

# server_health_check.sh 는 healthz/디스크/메모리/컨테이너/OOM 5가지를 하나의
# FAIL 로 합쳐 기록한다. 사유를 나눠 보고해야 'healthz 장애'로 오해하지 않는다.
count_reason() { printf '%s' "$fail_lines" | grep -c "$1"; }
f_health=$(count_reason 'healthz')
f_disk=$(count_reason '디스크')
f_mem=$(count_reason 'MB (<')
f_cont=$(count_reason '미실행')
f_oom=$(count_reason 'OOMKilled')

wt=$(docker logs --since 24h "$CONTAINER" 2>&1 | grep -c 'WORKER TIMEOUT')

msg="📊 [Clustead] 일일 요약 ${y} — 점검 ${checks}회 중 이상 ${fails}회 (healthz ${f_health} / 디스크 ${f_disk} / 메모리 ${f_mem} / 컨테이너 ${f_cont} / OOM ${f_oom}), 워커타임아웃(24h) ${wt}건"

ts=$(date '+%F %T')
echo "${ts} ${msg}" >> "$LOG"

if [ -n "$WEBHOOK" ]; then
  # Slack("text") / Discord("content") 양쪽 키 호환.
  payload=$(printf '{"text":%s,"content":%s}' "\"$msg\"" "\"$msg\"")
  curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$WEBHOOK" >/dev/null 2>&1
fi
exit 0
