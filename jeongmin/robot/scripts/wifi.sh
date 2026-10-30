#!/usr/bin/env bash
# 라즈베리파이 Wi-Fi 관리 (Raspberry Pi OS 의 NetworkManager / nmcli 사용).
# 집 Wi-Fi 로 SSH 접속한 상태에서, 학교·발표장에서 쓸 휴대폰 핫스팟을 "미리" 등록해 두는 용도.
#
#   bash wifi.sh status   지금 연결된 Wi-Fi 와 IP
#   bash wifi.sh list     저장된 Wi-Fi 와 우선순위
#   bash wifi.sh scan     주변 Wi-Fi (핫스팟이 보이는지 확인)
#   bash wifi.sh add      새 Wi-Fi 저장 (sudo 비밀번호 + Wi-Fi 비밀번호를 사람이 직접 입력)
#   bash wifi.sh remove   저장된 Wi-Fi 지우기
#
# 비밀번호는 라즈베리파이 안(/etc/NetworkManager/system-connections)에만 저장된다. 저장소에 적지 말 것.
set -euo pipefail

wifi_names() {  # 저장된 Wi-Fi 연결 이름들
  nmcli -t -f NAME,TYPE connection show | awk -F: '$2=="802-11-wireless"{print $1}'
}

active_name() {
  nmcli -t -f NAME,TYPE connection show --active | awk -F: '$2=="802-11-wireless"{print $1; exit}'
}

case "${1:-status}" in
  status)
    echo "연결된 Wi-Fi : $(active_name || true)"
    nmcli -t -f IN-USE,SSID,SIGNAL,CHAN device wifi list 2>/dev/null | awk -F: '$1=="*"{print "SSID / 신호 / 채널 : " $2 " / " $3 "% / " $4}'
    echo "IP           : $(hostname -I)"
    echo "주소         : http://$(hostname -I | awk '{print $1}'):8000  또는  http://$(hostname).local:8000"
    ;;
  list)
    printf '%-30s %s\n' "이름" "우선순위(높을수록 먼저)"
    while IFS= read -r name; do
      printf '%-30s %s\n' "$name" "$(nmcli -g connection.autoconnect-priority connection show "$name")"
    done < <(wifi_names)
    ;;
  scan)
    nmcli -f SSID,SIGNAL,CHAN,SECURITY device wifi list --rescan auto
    echo "※ 채널 1~13 = 2.4GHz, 36 이상 = 5GHz. 핫스팟이 안 보이면 휴대폰 핫스팟 화면을 켜 둔 채로 다시 실행."
    ;;
  add)
    read -rp "Wi-Fi 이름(SSID, 대소문자·띄어쓰기 그대로): " ssid
    [ -n "$ssid" ] || { echo "SSID 가 비었습니다"; exit 1; }
    read -rsp "Wi-Fi 비밀번호 (화면에 안 보임): " psk; echo
    [ ${#psk} -ge 8 ] || { echo "WPA 비밀번호는 8자 이상입니다"; exit 1; }
    read -rp "우선순위 [10] (둘 다 보이면 높은 쪽에 연결. 핫스팟 10, 집 0 추천): " prio
    prio=${prio:-10}
    name="wifi-$ssid"
    if wifi_names | grep -Fxq "$name"; then
      echo "이미 '$name' 이 있어 비밀번호·우선순위만 바꿉니다."
      sudo nmcli connection modify "$name" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$psk" \
        connection.autoconnect yes connection.autoconnect-priority "$prio"
    else
      sudo nmcli connection add type wifi con-name "$name" ifname wlan0 ssid "$ssid" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$psk" \
        connection.autoconnect yes connection.autoconnect-priority "$prio"
    fi
    unset psk
    echo "저장했습니다. 지금 연결은 그대로이고, 집 Wi-Fi 가 없는 곳에서 켜면 '$ssid' 에 자동 연결됩니다."
    echo "아이폰 핫스팟은 '호환성 최대화'를 켜 두세요 (WPA3 전용이면 연결이 안 될 수 있음)."
    bash "$0" list
    ;;
  remove)
    bash "$0" list
    read -rp "지울 이름: " name
    if [ "$name" = "$(active_name)" ]; then
      echo "지금 쓰는 Wi-Fi 라서 지우면 SSH 가 끊깁니다. 다른 Wi-Fi 로 접속했을 때 지우세요."
      exit 1
    fi
    sudo nmcli connection delete "$name"
    ;;
  *)
    sed -n '2,10p' "$0"
    exit 1
    ;;
esac
