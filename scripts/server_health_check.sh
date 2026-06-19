#!/usr/bin/env bash
# Clustead 서버 자가 점검 — cron 5분 간격 실행 권장.
#
# 외부 업타임 모니터(UptimeRobot 등)는 "사이트가 응답하는가"만 본다. 아직
# 사이트는 살아 있지만 곧 죽을 내부 신호(디스크 임박·메모리 고갈)나 컨테이너/
# healthz 상태는 못 본다. 이 스크립트가 그 사각지대를 보완한다.
#
# 알림은 상태가 '바뀔 때만' 보낸다(OK→이상, 이상내용 변경, 이상→복구) — 5분마다
# 같은 알림이 쏟아지지 않게.
#
# 설정: /etc/clustead-monitor.env (없으면 기본값). 예)
#   CLUSTEAD_ALERT_WEBHOOK="https://discord.com/api/webhooks/xxx"  # Slack/Discord 등
#   CLUSTEAD_DISK_MAX_PCT=90
#   CLUSTEAD_MEM_MIN_MB=80
#
# 설치(서버):
#   chmod +x /root/clustead/scripts/server_health_check.sh
#   ( crontab -l 2>/dev/null; echo "*/5 * * * * /root/clustead/scripts/server_health_check.sh" ) | crontab -
set -u

CONFIG=/etc/clustead-monitor.env
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && . "$CONFIG"

WEBHOOK="${CLUSTEAD_ALERT_WEBHOOK:-}"
DISK_MAX="${CLUSTEAD_DISK_MAX_PCT:-90}"
MEM_MIN_MB="${CLUSTEAD_MEM_MIN_MB:-80}"
CONTAINER="${CLUSTEAD_CONTAINER:-clustead-app-1}"
HEALTH_URL="${CLUSTEAD_HEALTH_URL:-http://127.0.0.1:8000/healthz}"
STATE_FILE="${CLUSTEAD_STATE_FILE:-/var/run/clustead-monitor.state}"
LOG="${CLUSTEAD_MONITOR_LOG:-/var/log/clustead-monitor.log}"

problems=()

# 1) 앱 컨테이너 실행 여부
if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
  problems+=("컨테이너 ${CONTAINER} 미실행")
fi

# 2) healthz (데이터 적재 완료 시 200, 부팅 워밍업/이상 시 503/000)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HEALTH_URL" 2>/dev/null || echo 000)
[ "$code" = "200" ] || problems+=("healthz HTTP ${code}")

# 3) 디스크 사용률(루트)
disk=$(df / | awk 'NR==2{gsub("%","",$5); print $5}')
if [ -n "$disk" ] && [ "$disk" -ge "$DISK_MAX" ]; then
  problems+=("디스크 ${disk}% (임계 ${DISK_MAX}%)")
fi

# 4) 가용 메모리(MB)
memav=$(free -m | awk '/^Mem:/{print $7}')
if [ -n "$memav" ] && [ "$memav" -lt "$MEM_MIN_MB" ]; then
  problems+=("가용메모리 ${memav}MB (<${MEM_MIN_MB}MB)")
fi

# 5) 직전 OOM-kill 흔적(컨테이너가 재시작됐어도 원인 가시화)
if docker inspect -f '{{.State.OOMKilled}}' "$CONTAINER" 2>/dev/null | grep -q true; then
  problems+=("컨테이너 OOMKilled 발생")
fi

ts=$(date '+%F %T')
if [ ${#problems[@]} -eq 0 ]; then
  status=OK
  msg=OK
else
  status=FAIL
  msg=$(printf '%s; ' "${problems[@]}")
fi

mkdir -p "$(dirname "$LOG")" 2>/dev/null
echo "${ts} [${status}] ${msg}" >> "$LOG"

notify() {
  [ -n "$WEBHOOK" ] || return 0
  # Slack("text") / Discord("content") 양쪽 키를 함께 보내 호환.
  local payload
  payload=$(printf '{"text":%s,"content":%s}' "\"$1\"" "\"$1\"")
  curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$WEBHOOK" >/dev/null 2>&1
}

last=$(cat "$STATE_FILE" 2>/dev/null || echo "")
cur="${status}:${msg}"

if [ "$status" = "FAIL" ] && [ "$last" != "$cur" ]; then
  notify "🔴 [Clustead] 이상 감지 — ${msg} (${ts})"
elif [ "$status" = "OK" ] && [ "${last%%:*}" = "FAIL" ]; then
  notify "✅ [Clustead] 정상 복구 (${ts})"
fi

echo "$cur" > "$STATE_FILE" 2>/dev/null
exit 0
