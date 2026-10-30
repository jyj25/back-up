"""가짜 모드용 작은 2D 세계. 노트북에서 '통 찾아가기' 를 하드웨어 없이 시험하려고 만들었다.

로봇은 (0,0) 에서 +x 방향을 보고 시작한다. 통(마커) 위치는 SIM_LAYOUT.
속도 값은 대충 정한 것이다 — 실제 로봇 값은 docs/robot-specs.md 에서 잰다.
"""
from __future__ import annotations

import math
import time

from .vision import Marker

# 마커 번호 → (x, y) 미터. 출발점은 뒤, 통 세 개는 앞에 나란히
SIM_LAYOUT = {0: (-0.8, 0.0), 1: (1.2, 0.6), 2: (1.2, 0.0), 3: (1.2, -0.6)}

M_PER_S_AT_100 = 0.25      # speed 100 일 때 직진 속도 (m/s)
DEG_PER_S_AT_100 = 90.0    # speed 100 일 때 제자리 회전 (°/s)
FOV_DEG = 66.0             # 카메라 모듈 3 가로 화각
MARKER_M = 0.10            # 인쇄한 마커 한 변 10cm
SEE_M = 3.0                # 이보다 멀면 마커가 안 보인다고 친다
ULTRA_DEG = 12.0           # 초음파가 보는 폭 (±)

# 이동 이름 → (앞 성분, 왼쪽 성분, 회전 방향 +1=왼쪽)
_MOTION = {
    "forward": (1, 0, 0), "backward": (-1, 0, 0),
    "strafe_left": (0, 1, 0), "strafe_right": (0, -1, 0),
    "diag_forward_left": (0.7, 0.7, 0), "diag_forward_right": (0.7, -0.7, 0),
    "diag_backward_left": (-0.7, 0.7, 0), "diag_backward_right": (-0.7, -0.7, 0),
    "turn_left": (0, 0, 1), "turn_right": (0, 0, -1),
}


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class World:
    def __init__(self, layout: dict[int, tuple[float, float]] | None = None, clock=time.monotonic) -> None:
        self.layout = dict(layout or SIM_LAYOUT)
        self.clock = clock
        self.x = self.y = self.heading = 0.0  # heading: 라디안, 0 = +x, 왼쪽으로 돌면 +
        self.action: str | None = None
        self.speed = 0
        self._t = clock()

    def set_clock(self, clock) -> None:
        self._advance()
        self.clock, self._t = clock, clock()

    def _advance(self) -> None:
        now = self.clock()
        dt, self._t = now - self._t, now
        if not self.action or dt <= 0:
            return
        fwd, left, turn = _MOTION[self.action]
        v = self.speed / 100 * M_PER_S_AT_100
        self.heading = _wrap(self.heading + turn * math.radians(self.speed / 100 * DEG_PER_S_AT_100) * dt)
        c, s = math.cos(self.heading), math.sin(self.heading)
        self.x += (fwd * c - left * s) * v * dt
        self.y += (fwd * s + left * c) * v * dt

    def set_motion(self, action: str | None, speed: int) -> None:
        self._advance()
        self.action, self.speed = action, speed

    def _seen(self):
        """(마커 번호, 거리 m, 방향 라디안: + 는 왼쪽) — 로봇 기준"""
        self._advance()
        for mid, (mx, my) in self.layout.items():
            dx, dy = mx - self.x, my - self.y
            yield mid, math.hypot(dx, dy), _wrap(math.atan2(dy, dx) - self.heading)

    def markers(self) -> list[Marker]:
        half = math.radians(FOV_DEG / 2)
        found = []
        for mid, d, bearing in self._seen():
            if 0.05 < d < SEE_M and abs(bearing) < half:
                size = MARKER_M / (2 * d * math.tan(half))
                found.append(Marker(mid, round(-bearing / half, 3), round(min(size, 1.0), 3)))
        return sorted(found, key=lambda m: -m.size)

    def distance_cm(self) -> float:
        ahead = [d for _, d, b in self._seen() if abs(b) < math.radians(ULTRA_DEG)]
        return round(min(ahead) * 100, 1) if ahead else 200.0

    def pose(self) -> dict:
        self._advance()
        return {"x": round(self.x, 3), "y": round(self.y, 3), "heading_deg": round(math.degrees(self.heading), 1)}
