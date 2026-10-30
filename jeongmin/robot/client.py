"""다른 역할(AI·웹·앱)이 파이썬에서 로봇을 부를 때 쓰는 작은 클라이언트. 설치할 것 없음 (표준 라이브러리만).

    from client import RobotClient
    bot = RobotClient("http://<라즈베리파이 IP>:8000")
    bot.move("forward", speed=100, seconds=1.5)   # 1.5초 앞으로 (끝날 때까지 기다림)
    bot.beep(); bot.led("green")
    print(bot.distance())                         # 앞 거리 cm
    bot.go("can")                                  # 캔 통 찾아가서 쏟고 출발점으로 (끝날 때까지 기다림)

노트북에서 가짜 서버로 먼저 시험: ROBOT_MODE=fake uvicorn server.main:app --port 8000
그리고 python client.py  → 간단한 동작 확인
"""
from __future__ import annotations

import json
import time
import urllib.request


class RobotClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 3.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def status(self) -> dict:
        return self._call("GET", "/api/status")

    def move(self, action: str, speed: int = 100, seconds: float = 0.5) -> dict:
        """seconds 동안 움직이고 멈춘다. 3초보다 길면 0.3초마다 명령을 다시 보낸다 (서버는 3초 뒤 자동 정지)."""
        end = time.monotonic() + seconds
        s = {}
        while (left := end - time.monotonic()) > 0:
            s = self._call("POST", "/api/move", {"action": action, "speed": speed,
                                                 "duration_ms": max(50, min(int(left * 1000), 500))})
            if s.get("blocked"):  # 앞에 장애물 → 서버가 멈춤
                break
            time.sleep(min(0.3, left))
        self.stop()
        return s

    def stop(self) -> dict:
        return self._call("POST", "/api/stop")

    def servo(self, pan: int | None = None, tilt: int | None = None) -> dict:
        return self._call("POST", "/api/servo", {"pan": pan, "tilt": tilt})

    def distance(self) -> float:
        return self._call("GET", "/api/distance")["cm"]

    def line(self) -> list[bool]:
        return self._call("GET", "/api/line")["sensors"]

    def beep(self, ms: int = 150) -> None:
        self._call("POST", "/api/beep", {"ms": ms})

    def led(self, color: str | None) -> dict:
        return self._call("POST", "/api/led", {"color": color})

    # ---- 통 찾아가기 (stations.json) ----

    def stations(self) -> dict:
        return self._call("GET", "/api/stations")

    def go(self, station: str, dump: bool = True, return_home: bool = True,
           wait: bool = True, timeout: float = 180) -> dict:
        """station 으로 가서 (쏟고) (출발점으로). AI 가 분류 결과로 station 이름만 정해서 부르면 된다.
        wait=True 면 끝날 때까지 기다리고 마지막 상태를 돌려준다 (phase: done / failed / cancelled)."""
        self._call("POST", "/api/mission", {"station": station, "dump": dump, "return_home": return_home})
        if not wait:
            return self.mission()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            m = self.mission()
            if not m["running"]:
                return m
            time.sleep(0.5)
        self.cancel_mission()
        return self.mission()

    def mission(self) -> dict:
        return self._call("GET", "/api/mission")

    def cancel_mission(self) -> dict:
        return self._call("POST", "/api/mission/cancel")

    def snapshot(self, path: str = "snapshot.jpg") -> str:
        """카메라 사진 한 장을 파일로 저장 (AI 역할이 인식에 쓸 때)"""
        with urllib.request.urlopen(self.base + "/api/camera.jpg", timeout=self.timeout) as r:
            open(path, "wb").write(r.read())
        return path


if __name__ == "__main__":
    import sys

    bot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000")
    print("상태", bot.status())
    print("앞으로 1초", bot.move("forward", 80, 1.0))
    print("거리", bot.distance(), "cm / 라인", bot.line())
    bot.led("blue"); bot.beep(100); bot.led(None)
    print("끝", bot.status())
