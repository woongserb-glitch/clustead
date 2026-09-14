#!/bin/sh
# 워커 메모리 추이 기록 — 재활용(max_requests)을 꺼도 되는지 판단할 근거를 모은다.
#
# 배경: 2026-07-19 에 워커 재활용을 껐다가(스왑 콜드스타트 회피) 07-25 에 되켰다
# ("재활용 OFF 상태에서 워커 메모리가 며칠 누적 → 스왑 스톰"). 그 누적이 실제로
# 일어나는지 측정한 기록이 없어서, 끄는 판단을 근거 없이 하게 된다.
#
# 워커가 나이를 먹을수록 RSS+Swap 이 우상향하면 누적이 실재하는 것이고, 평탄하면
# 재활용을 꺼도 된다. 재활용 주기가 약 1.7 일이므로 최소 한 주는 모아야 한다.
#
# CSV 한 줄 = 한 프로세스의 한 시점. 10 분마다 3 줄 남짓, 하루 ~30KB.
#
# 설치: crontab -e 에
#   */10 * * * * /root/clustead/scripts/log_worker_memory.sh
set -eu

OUT="${CLUSTEAD_MEM_LOG:-/var/log/clustead-worker-mem.csv}"
MAX_LINES="${CLUSTEAD_MEM_LOG_MAX:-20000}"   # 약 6 주분. 넘으면 앞에서 자른다.

[ -f "$OUT" ] || echo "ts,role,pid,age_s,rss_kb,swap_kb,host_avail_mb,host_swap_used_mb" > "$OUT"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
AVAIL="$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo)"
SWTOT="$(awk '/^SwapTotal:/{print $2}' /proc/meminfo)"
SWFREE="$(awk '/^SwapFree:/{print $2}' /proc/meminfo)"
SWUSED="$(( (SWTOT - SWFREE) / 1024 ))"

# gunicorn 프로세스 집합. 부모가 같은 집합에 있으면 워커, 아니면 마스터.
PIDS="$(pgrep -f 'gunicorn' 2>/dev/null || true)"
[ -n "$PIDS" ] || exit 0

for PID in $PIDS; do
    [ -r "/proc/$PID/status" ] || continue
    RSS="$(awk '/^VmRSS:/{print $2}' "/proc/$PID/status" 2>/dev/null || echo)"
    [ -n "$RSS" ] || continue
    SWAP="$(awk '/^VmSwap:/{print $2}' "/proc/$PID/status" 2>/dev/null || echo 0)"
    AGE="$(ps -o etimes= -p "$PID" 2>/dev/null | tr -d ' ' || echo)"
    [ -n "$AGE" ] || continue
    PPID_V="$(awk '{print $4}' "/proc/$PID/stat" 2>/dev/null || echo 0)"

    ROLE=master
    for P in $PIDS; do
        [ "$P" = "$PPID_V" ] && ROLE=worker && break
    done

    echo "$TS,$ROLE,$PID,$AGE,$RSS,$SWAP,$AVAIL,$SWUSED" >> "$OUT"
done

# 무한정 자라지 않게 앞에서 자른다.
LINES="$(wc -l < "$OUT")"
if [ "$LINES" -gt "$MAX_LINES" ]; then
    HEAD="$(head -1 "$OUT")"
    TAIL_N="$(( MAX_LINES / 2 ))"
    { echo "$HEAD"; tail -n "$TAIL_N" "$OUT"; } > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
fi
