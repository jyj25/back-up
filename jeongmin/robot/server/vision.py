"""카메라 화면에서 ArUco 마커(통마다 붙인 번호표)를 찾는다.

- CameraVision: 실제 카메라 화면을 OpenCV 로 분석 (라즈베리파이)
- SimVision:   가짜 모드에서 sim.World 가 계산한 마커를 돌려준다 (노트북)

마커 하나 = Marker(id, cx, size)
  cx   : 화면 가로 위치. -1 = 왼쪽 끝, 0 = 가운데, +1 = 오른쪽 끝
  size : 마커 너비 / 화면 너비. 가까울수록 커진다 (10cm 마커가 약 25cm 앞이면 0.3 정도)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

MARKER_DICT = "DICT_4X4_50"  # 4x4 칸, 0~49번. 인쇄용 scripts/make_markers.py 와 같아야 한다


@dataclass
class Marker:
    id: int
    cx: float
    size: float

    def to_dict(self) -> dict:
        return asdict(self)


def make_detector():
    import cv2

    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, MARKER_DICT))
    return cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())


def detect(frame, detector=None) -> list[Marker]:
    """BGR 또는 흑백 이미지(numpy) → 보이는 마커들 (큰 것부터)"""
    import cv2

    detector = detector or make_detector()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return []
    w = gray.shape[1]
    found = []
    for c, i in zip(corners, ids.flatten()):
        pts = c.reshape(4, 2)
        xs = pts[:, 0]
        width = max(xs) - min(xs)
        found.append(Marker(int(i), round(float(xs.mean() / w * 2 - 1), 3), round(float(width / w), 3)))
    return sorted(found, key=lambda m: -m.size)


class CameraVision:
    def __init__(self, camera) -> None:
        self.camera = camera
        self._detector = None

    def markers(self) -> list[Marker]:
        frame = self.camera.frame()
        if frame is None:
            return []
        if self._detector is None:
            self._detector = make_detector()
        return detect(frame, self._detector)


class SimVision:
    def __init__(self, world) -> None:
        self.world = world

    def markers(self) -> list[Marker]:
        return self.world.markers()


class NoVision:
    def markers(self) -> list[Marker]:
        return []
