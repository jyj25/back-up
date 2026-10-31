"""카메라: 라즈베리파이 카메라 모듈 3(picamera2) → USB 웹캠(OpenCV) 순서로 찾는다. 둘 다 없으면 None.

CAMERA=picamera|usb|none 으로 고를 수 있다. USB 웹캠 번호는 CAMERA_INDEX (기본 0).
"""
from __future__ import annotations

import os
import threading
import time


class Camera:
    def __init__(self) -> None:
        self.kind = "none"
        self._lock = threading.Lock()
        self._picam = None
        self._cap = None
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

            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self._cap, self.kind = cap, "usb"
        except Exception as e:
            print(f"[camera] OpenCV 웹캠 사용 불가: {e}")

    def frame(self):
        """지금 화면 (BGR numpy 배열). 카메라가 없으면 None."""
        with self._lock:
            if self.kind == "picamera":
                return self._picam.capture_array()  # RGB888 은 실제로 BGR 순서라 OpenCV 에 그대로 넣는다
            if self.kind == "usb":
                ok, frame = self._cap.read()
                return frame if ok else None
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
            self._cap.release()
