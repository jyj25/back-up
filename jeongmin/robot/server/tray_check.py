"""샤오(ESP32S3) 카메라로 트레이 위 물건을 본다: 빈 트레이 사진과 비교해 물건이 있는지·어디 있는지 알려 준다.

stations.json 의 "tray" 로 조절 (모두 선택):
  roi        트레이 영역 [x0,y0,x1,y1] (0~1, 화면 비율). 기본 전체
  drop_zone  쏟으면 물건이 떨어지는 위치 [x0,y0,x1,y1]. 기본 roi 전체 (조립 후 실제 위치에 맞게 줄일 것)
  diff       밝기 차이 기준 (기본 30)    min_area  물건으로 볼 최소 면적 비율 (기본 0.02)
빈 트레이일 때 POST /api/tray/baseline 으로 기준 사진을 저장해 둔다.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class TrayCheck:
    def __init__(self, cam, path: Path, conf: dict | None = None) -> None:
        c = conf or {}
        self.cam, self.path = cam, Path(path)
        self.roi = tuple(c.get("roi", (0.0, 0.0, 1.0, 1.0)))
        self.drop_zone = tuple(c.get("drop_zone", self.roi))
        self.diff = int(c.get("diff", 30))
        self.min_area = float(c.get("min_area", 0.02))
        self._base = None
        if self.path.exists():
            img = cv2.imread(str(self.path))
            if img is not None:
                self._base = self._gray(img)

    @staticmethod
    def _gray(img):
        return cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (7, 7), 0)

    @property
    def ready(self) -> bool:
        return self.cam is not None and self._base is not None

    def _frame(self):
        data = self.cam.jpeg() if self.cam else None
        if not data:
            return None
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    def set_baseline(self) -> bool:
        img = self._frame()
        if img is None:
            return False
        cv2.imwrite(str(self.path), img)
        self._base = self._gray(img)
        return True

    def look(self) -> dict | None:
        """{present, area, cx, cy, in_zone}. 기준 사진이 없거나 사진을 못 받으면 None."""
        if not self.ready:
            return None
        img = self._frame()
        if img is None:
            return None
        g = self._gray(img)
        if g.shape != self._base.shape:
            return None
        _, m = cv2.threshold(cv2.absdiff(g, self._base), self.diff, 255, cv2.THRESH_BINARY)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        h, w = m.shape
        x0, y0, x1, y1 = self.roi
        ox, oy = int(x0 * w), int(y0 * h)
        roi = m[oy:int(y1 * h), ox:int(x1 * w)]
        area = float(np.count_nonzero(roi)) / max(1, roi.size)
        out = {"present": area >= self.min_area, "area": round(area, 3), "cx": None, "cy": None, "in_zone": None}
        if out["present"]:
            ys, xs = np.nonzero(roi)
            cx, cy = (xs.mean() + ox) / w, (ys.mean() + oy) / h
            zx0, zy0, zx1, zy1 = self.drop_zone
            out.update(cx=round(float(cx), 3), cy=round(float(cy), 3), in_zone=bool(zx0 <= cx <= zx1 and zy0 <= cy <= zy1))
        return out
