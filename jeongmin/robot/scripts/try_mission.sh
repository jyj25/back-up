#!/usr/bin/env bash
# 실제 로봇으로 통 찾아가기 한 번 시험 (라즈베리파이에서). 조종 서버를 다시 켜고 임무를 보내 진행을 한 줄씩 보여 준다.
#
#   bash scripts/try_mission.sh can                 캔 통 → 쏟기 → 출발점 (stations.json)
#   STATIONS_FILE=stations.blocks.json bash scripts/try_mission.sh can   키트 블록으로
#   DUMP=false HOME_BACK=false bash scripts/try_mission.sh can            가기만
#
# 비상 정지: 리모컨 전원 버튼. LIMIT 초(기본 120)가 지나면 취소한다.
set -uo pipefail
cd "$(dirname "$0")/.."
STATION=${1:-can}
LIMIT=${LIMIT:-120}
M=localhost:8000

# 이 셸이 아니라 uvicorn 프로세스만 끈다 (pkill -f "uvicorn server.main" 은 이 명령을 실행한 셸도 잡는다)
pkill -f "^$HOME/raspbot-venv/bin/python.*uvicorn" ; sleep 1
BOARD_PORT=${BOARD_PORT:-none} HISTORY_FILE=${HISTORY_FILE:-none} \
  nohup "$HOME/raspbot-venv/bin/uvicorn" server.main:app --host 0.0.0.0 --port 8000 > /tmp/robot.log 2>&1 &
for _ in $(seq 1 40); do curl -s $M/api/status >/dev/null && break; sleep 0.5; done

show='import sys,json;d=json.load(sys.stdin);print(", ".join("#%d(x=%+.2f,size=%.3f)"%(m["id"],m["cx"],m["size"]) for m in d.get("markers") or d.get("seen") or []) or "-")'
echo "카메라: $(curl -s $M/api/status | python3 -c 'import sys,json;print(json.load(sys.stdin)["camera"])')  보이는 마커: $(curl -s $M/api/markers | python3 -c "$show")"
echo "5초 뒤 출발: $STATION"; sleep 5
curl -s -X POST $M/api/mission -H "Content-Type: application/json" \
  -d "{\"station\":\"$STATION\",\"dump\":${DUMP:-true},\"return_home\":${HOME_BACK:-true}}" >/dev/null
last=""; t0=$(date +%s)
while :; do
  line=$(curl -s $M/api/mission | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["phase"],"->",d["target"],"걸음",d["steps"],d["message"])')
  key=$(echo "$line" | cut -d' ' -f1-3)
  [ "$key" != "$last" ] && echo "$(( $(date +%s)-t0 ))s $line"; last="$key"
  case "${line%% *}" in done|failed|cancelled) break;; esac
  if [ $(( $(date +%s)-t0 )) -ge "$LIMIT" ]; then curl -s -X POST $M/api/mission/cancel >/dev/null; echo "${LIMIT}초 초과 → 취소"; break; fi
  sleep 0.3
done
curl -s -X POST $M/api/stop >/dev/null
echo "끝: $(curl -s $M/api/mission | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["phase"],d["message"])')  (서버는 켜 둠, 로그 /tmp/robot.log)"
