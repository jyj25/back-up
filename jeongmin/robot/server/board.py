"""XIAO ESP32S3(분류 보드)를 USB 시리얼로 읽는다.

BOARD_PORT
  auto  /dev/ttyACM* 중 첫 번째 (실제 로봇 기본값)
  none  읽지 않음 (가짜 모드 기본값)
  그 외  포트 이름 그대로 (/dev/ttyACM0, COM4 …)

포트가 없거나 뽑히면 2초마다 다시 찾는다. 읽은 줄은 on_line(문자열) 으로 넘긴다 — 해석은 sorter.parse_line.
라즈베리파이에서 권한 오류가 나면 사용자를 dialout 그룹에 넣는다 (사람이 sudo 로).
"""
from __future__ import annotations

import glob
import threading
import time
from datetime import datetime


class BoardReader:
    def __init__(self, port: str, on_line, baud: int = 115200) -> None:
        self.want, self.on_line, self.baud = port, on_line, baud
        self.port: str | None = None     # 지금 연결된 포트
        self.error: str | None = None
        self.last_line_at: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self.want.lower() != "none"

    def start(self) -> None:
        if not self.enabled:
            return
        try:
            import serial  # noqa: F401  pyserial
        except ImportError:
            self.error = "pyserial 없음 (pip install pyserial)"
            print(f"[board] {self.error}")
            return
        self._thread = threading.Thread(target=self._run, name="board-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {"want": self.want, "port": self.port, "error": self.error, "last_line_at": self.last_line_at}

    def _find(self) -> str | None:
        if self.want.lower() != "auto":
            return self.want
        ports = sorted(glob.glob("/dev/ttyACM*"))
        return ports[0] if ports else None

    def _run(self) -> None:
        import serial

        while not self._stop.is_set():
            path = self._find()
            if not path:
                self.error = "보드를 찾지 못함 (USB 연결 확인)"
                self._stop.wait(2)
                continue
            try:
                with serial.Serial(path, self.baud, timeout=1) as s:
                    self.port, self.error = path, None
                    print(f"[board] 연결: {path}")
                    while not self._stop.is_set():
                        raw = s.readline()
                        if raw:
                            self.last_line_at = datetime.now().isoformat(timespec="seconds")
                            self.on_line(raw.decode("utf-8", errors="replace"))
            except (OSError, serial.SerialException) as e:
                self.error = f"{path}: {e}"
                print(f"[board] {self.error}")
            self.port = None
            self._stop.wait(2)
