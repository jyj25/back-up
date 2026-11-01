#!/usr/bin/env bash
# 라즈베리파이를 켜면 조종 서버(8000번 포트)가 자동으로 뜨게 한다 (systemd 서비스 "raspbot").
# 발표장에서 SSH 없이 전원만 켜고 휴대폰으로 http://<IP>:8000 에 들어가기 위한 것.
#
#   bash autostart.sh install    켜기 (sudo 비밀번호는 사람이 입력)
#   bash autostart.sh uninstall  끄기
#   bash autostart.sh status     상태와 최근 로그
#
# 사용자 이름·경로는 실행할 때 자동으로 채운다 (저장소에는 적지 않는다).
set -euo pipefail

ROBOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
VENV=${VENV:-$HOME/raspbot-venv}
UNIT=/etc/systemd/system/raspbot.service

case "${1:-status}" in
  install)
    [ -x "$VENV/bin/uvicorn" ] || { echo "$VENV/bin/uvicorn 이 없습니다: $VENV/bin/pip install \"fastapi[standard]\""; exit 1; }
    sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Raspbot 조종 서버
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$ROBOT_DIR
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$ROBOT_DIR/robot.env
ExecStart=$VENV/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 2
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now raspbot
    echo "켰습니다. 다음부터 라즈베리파이를 켜면 조종 서버가 자동으로 뜹니다."
    echo "직접 uvicorn 을 실행할 때는 포트가 겹치니 먼저: sudo systemctl stop raspbot"
    echo "설정(CORS_ORIGINS, MAX_SPEED 등)은 $ROBOT_DIR/robot.env 에 적고: sudo systemctl restart raspbot"
    ;;
  uninstall)
    sudo systemctl disable --now raspbot || true
    sudo rm -f "$UNIT"
    sudo systemctl daemon-reload
    echo "자동 실행을 껐습니다."
    ;;
  status)
    systemctl is-enabled raspbot 2>/dev/null || echo "자동 실행 안 함"
    systemctl --no-pager status raspbot 2>/dev/null | head -5 || true
    journalctl -u raspbot -n 15 --no-pager 2>/dev/null || true
    ;;
  *)
    sed -n '2,8p' "$0"
    exit 1
    ;;
esac
