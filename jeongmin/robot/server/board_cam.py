"""XIAO 보드 카메라 사진을 USB 시리얼로 받는다 (보드에 사진 수집용 펌웨어 xiao_stream 이 있을 때).

보드에 'C' 한 글자를 보내면 [AA 55 AA 55][길이 u32 LE][JPEG] 로 한 장이 온다 (yujeong/firmware/xiao_stream, IF-01 수집용).
판정 펌웨어가 들어가면 사진 대신 판정 JSON 이 오므로 이 기능은 None 을 돌려준다.
같은 포트를 판정 읽기(BoardReader)가 쓰고 있으면 쓰지 않는다 — BOARD_PORT=none 일 때 시연·확인용.
"""
from __future__ import annotations

import glob
import struct
import threading
import time

HEAD = b"\xAA\x55\xAA\x55"


class BoardCamera:
    def __init__(self, port: str = "auto", baud: int = 115200) -> None:
        self.want, self.baud = port, baud
        self._ser = None
        self._lock = threading.Lock()

    def _open(self):
        if self._ser is not None:
            return self._ser
        import serial  # pyserial

        path = self.want
        if path.lower() == "auto":
            ports = sorted(glob.glob("/dev/ttyACM*"))
            if not ports:
                return None
            path = ports[0]
        self._ser = serial.Serial(path, self.baud, timeout=0.5)
        time.sleep(0.2)
        self._ser.reset_input_buffer()
        return self._ser

    def jpeg(self, timeout: float = 3.0) -> bytes | None:
        """한 장. 보드가 없거나 사진을 안 보내면 None."""
        with self._lock:
            try:
                ser = self._open()
                if ser is None:
                    return None
                ser.reset_input_buffer()
                ser.write(b"C")
                buf, t0 = b"", time.monotonic()
                while time.monotonic() - t0 < timeout:
                    buf += ser.read(ser.in_waiting or 1)
                    i = buf.find(HEAD)
                    if i >= 0 and len(buf) >= i + 8:
                        n = struct.unpack("<I", buf[i + 4:i + 8])[0]
                        if not 0 < n < 500_000:
                            return None
                        while len(buf) < i + 8 + n and time.monotonic() - t0 < timeout:
                            buf += ser.read(i + 8 + n - len(buf))
                        data = buf[i + 8:i + 8 + n]
                        return data if len(data) == n and data[:2] == b"\xff\xd8" else None
                return None
            except Exception as e:  # 뽑힘·권한 등 → 다음에 다시 연다
                print(f"[board-cam] {e}")
                self.close()
                return None

    def frames(self, fps: float = 4):
        """MJPEG 스트림용. 사진이 안 오면 끝낸다."""
        misses = 0
        while misses < 3:
            data = self.jpeg()
            if data is None:
                misses += 1
                continue
            misses = 0
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            time.sleep(1 / fps)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None
