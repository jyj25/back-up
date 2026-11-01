"""카메라: 라즈베리파이 카메라 모듈 3(picamera2) → USB 웹캠(OpenCV) 순서로 찾는다. 둘 다 없으면 None.

CAMERA=picamera|usb|none 으로 고를 수 있다. USB 웹캠 번호는 CAMERA_INDEX (기본 0).
"""
from __future__ import annotations

import os
import sys
import threading
import time


class Camera:
    def __init__(self) -> None:
        self.kind = "none"
        self._lock = threading.Lock()
        self._picam = None
        self._cap = None
        self._latest = None  # USB 웹캠: 읽기 스레드가 계속 갱신하는 최신 화면
        self._running = False
        want = os.environ.get("CAMERA", "auto").lower()
        if want in ("auto", "picamera"):
            self._try_picamera()
        if self.kind == "none" and want in ("auto", "usb"):
            self._try_opencv(int(os.environ.get("CAMERA_INDEX", "0")))

    def _try_picamera(self) -> None:
        try:
            from picamera2 import Picamera2

            # libcamera 는 USB 웹캠(uvcvideo)도 목록에 넣는다 → MJPEG 라 RGB 로 못 받으므로 USB 는 OpenCV 로 넘긴다
            csi = [i for i, c in enumerate(Picamera2.global_camera_info()) if "usb" not in c.get("Id", "")]
            if not csi:
                return
            cam = Picamera2(csi[0])
            cam.configure(cam.create_video_configuration(main={"size": (640, 480), "format": "RGB888"}))
            cam.start()
            self._picam, self.kind = cam, "picamera"
        except Exception as e:
            print(f"[camera] picamera2 사용 불가: {e}")

    def _try_opencv(self, index: int) -> None:
        try:
            import cv2

            # 리눅스는 V4L2 로 바로 연다 (기본값은 다른 방식부터 시도하다 실패하기도 함).
            # 서버를 껐다 바로 켜면 이전 프로세스가 카메라를 아직 쥐고 있을 수 있어 몇 번 다시 시도
            backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
            for _ in range(5):
                cap = cv2.VideoCapture(index, backend)
                if cap.isOpened():
                    break
                cap.release()
                time.sleep(0.5)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self._cap, self.kind = cap, "usb"
                # 웹캠은 사진을 몇 장 쌓아 두므로 read() 한 번이면 예전 화면이 나온다
                # → 계속 읽어 최신 한 장만 들고 있는다 (돌린 직후에도 지금 화면으로 판단)
                self._running = True
                threading.Thread(target=self._read_loop, daemon=True).start()
        except Exception as e:
            print(f"[camera] OpenCV 웹캠 사용 불가: {e}")

    def _read_loop(self) -> None:
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                self._latest = frame
            else:
                time.sleep(0.05)

    def frame(self):
        """지금 화면 (BGR numpy 배열). 카메라가 없으면 None."""
        with self._lock:
            if self.kind == "picamera":
                return self._picam.capture_array()  # RGB888 은 실제로 BGR 순서라 OpenCV 에 그대로 넣는다
            if self.kind == "usb":
                for _ in range(20):  # 막 켜졌으면 첫 장을 잠깐 기다린다
                    if self._latest is not None:
                        break
                    time.sleep(0.05)
                return self._latest
            return None

    def jpeg(self, quality: int = 80) -> bytes | None:
        """지금 화면을 JPEG 한 장으로. 카메라가 없으면 None."""
        frame = self.frame()
        if frame is None:
            return None
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def frames(self, fps: float = 15):
        """MJPEG 스트림용 프레임 생성기"""
        delay = 1 / fps
        while True:
            data = self.jpeg()
            if data is None:
                return
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            time.sleep(delay)

    def close(self) -> None:
        if self._picam is not None:
            self._picam.stop()
        if self._cap is not None:
            self._running = False
            time.sleep(0.1)
            self._cap.release()
