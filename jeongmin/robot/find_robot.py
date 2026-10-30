"""같은 Wi-Fi(휴대폰 핫스팟 등)에 있는 로봇을 찾는다. 노트북에서 실행, 설치할 것 없음.

    python find_robot.py            내 IP 대역(/24)에서 8000번(조종 서버)·22번(SSH) 이 열린 기기 찾기
    python find_robot.py 172.20.10  대역을 직접 지정 (아이폰 핫스팟은 보통 172.20.10.x)

핫스팟에서는 IP 가 매번 바뀌고, Windows 에서는 '이름.local' 이 안 될 때가 많아서 만든 것.
"""
from __future__ import annotations

import json
import socket
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def my_prefixes() -> list[str]:
    """이 노트북의 IPv4 앞 세 자리들 (예: '192.168.0')"""
    ips = set()
    try:  # 기본 경로로 나가는 IP (실제로 패킷을 보내지는 않음)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass  # 핫스팟에 인터넷이 없을 때
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ips.add(info[4][0])
    return sorted({ip.rsplit(".", 1)[0] for ip in ips if not ip.startswith(("127.", "169.254."))})


def is_open(ip: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def robot_status(ip: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{ip}:8000/api/status", timeout=1.5) as r:
            s = json.loads(r.read())
        return s if "mode" in s and "moving" in s else None
    except Exception:
        return None


def scan(prefix: str) -> list[tuple[str, dict | None, bool]]:
    ips = [f"{prefix}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(64) as pool:
        web = list(pool.map(lambda ip: is_open(ip, 8000), ips))
        ssh = list(pool.map(lambda ip: is_open(ip, 22), ips))
    found = []
    for ip, w, s in zip(ips, web, ssh):
        st = robot_status(ip) if w else None
        if st or s:
            found.append((ip, st, s))
    return found


def main() -> None:
    prefixes = sys.argv[1:] or my_prefixes()
    if not prefixes:
        print("네트워크에 연결돼 있지 않습니다. 로봇과 같은 Wi-Fi(핫스팟)에 연결하세요.")
        return
    any_robot = False
    for p in prefixes:
        print(f"{p}.1~254 찾는 중...")
        for ip, st, ssh in scan(p):
            if st:
                any_robot = True
                print(f"  ★ 로봇 조종 서버: http://{ip}:8000  (mode={st['mode']}, camera={st['camera']})")
            else:
                print(f"  - SSH 열린 기기: {ip}  (조종 서버가 꺼진 라즈베리파이일 수 있음 → ssh <사용자>@{ip})")
    if not any_robot:
        print("조종 서버를 못 찾았습니다. 라즈베리파이가 켜졌는지(부팅 1분), 같은 Wi-Fi 인지, 자동 실행(autostart.sh)을 켰는지 확인.")


if __name__ == "__main__":
    main()
