import asyncio
import math
import os
import time

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server import main  # noqa: E402
from server.navigator import NavConfig, decide  # noqa: E402
from server.sim import SIM_LAYOUT  # noqa: E402
from server.vision import Marker  # noqa: E402

CFG = NavConfig()


# ---- 한 걸음 판단 ----

def test_decide_search_turns_toward_last_seen_side():
    assert decide([], 1, 200, CFG).action == "turn_left"
    assert decide([], 1, 200, CFG, last_cx=0.5).action == "turn_right"
    assert decide([Marker(2, 0, 0.1)], 1, 200, CFG).phase == "search"  # 다른 마커는 무시


def test_decide_align_approach_arrive():
    s = decide([Marker(1, 0.6, 0.1)], 1, 200, CFG)
    assert (s.phase, s.action) == ("align", "turn_right") and 60 <= s.ms <= CFG.pulse_ms
    assert decide([Marker(1, -0.6, 0.1)], 1, 200, CFG).action == "turn_left"
    assert decide([Marker(1, 0.05, 0.1)], 1, 200, CFG).action == "forward"
    assert decide([Marker(1, 0.05, 0.35)], 1, 200, CFG).phase == "arrived"   # 마커가 큼
    assert decide([Marker(1, 0.05, 0.1)], 1, 20, CFG).phase == "arrived"     # 초음파 가까움
    assert decide([Marker(1, 0.6, 0.1)], 1, 20, CFG).phase == "align"        # 옆을 보고 있으면 초음파는 무시


# ---- 실제 영상에서 마커 찾기 (OpenCV) ----

def test_detect_printed_markers():
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from server.vision import detect

    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    frame = np.full((480, 640), 255, np.uint8)
    frame[40:240, 400:600] = cv2.aruco.generateImageMarker(d, 1, 200)   # 오른쪽에 크게
    frame[300:380, 60:140] = cv2.aruco.generateImageMarker(d, 3, 80)    # 왼쪽에 작게
    found = detect(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    assert [m.id for m in found] == [1, 3]
    assert found[0].cx > 0.3 and abs(found[0].size - 200 / 640) < 0.02
    assert found[1].cx < -0.5


def test_detect_kit_block_apriltags():
    # 라즈봇 키트 블록 윗면은 AprilTag 36h11 (stations.blocks.json)
    cv2 = pytest.importorskip("cv2")
    import json
    import numpy as np

    from server.vision import detect, make_detector

    conf = json.loads((main.STATIONS_FILE.parent / "stations.blocks.json").read_text(encoding="utf-8"))
    assert {s["marker"] for s in conf["stations"].values()} == {1, 2, 3, 4}
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, conf["marker_dict"]))
    frame = np.full((480, 640), 255, np.uint8)
    frame[100:220, 100:220] = cv2.aruco.generateImageMarker(d, 2, 120)
    frame[100:220, 400:520] = cv2.aruco.generateImageMarker(d, 4, 120)
    assert sorted(m.id for m in detect(frame, make_detector(conf["marker_dict"]))) == [2, 4]
    assert detect(frame) == []  # 기본(4x4) 마커로는 안 보인다


# ---- 가짜 세계에서 임무 전체 (가상 시계라 바로 끝남) ----

class VirtualClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += s
        await asyncio.sleep(0)


def test_full_mission_in_sim():
    robot = main.Robot()
    clock = VirtualClock()
    world = robot.driver.world
    world.set_clock(clock)
    robot.mission.sleep = clock.sleep
    dumped_at = []
    robot.driver.dump = lambda: dumped_at.append(world.pose())

    async def run():
        robot.mission.start("can")
        await asyncio.wait_for(robot.mission.wait(), 20)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    st = robot.mission.state
    assert st["phase"] == "done", st
    (p,) = dumped_at
    bx, by = SIM_LAYOUT[1]  # 캔 통
    assert 0.15 < math.hypot(bx - p["x"], by - p["y"]) < 0.35   # 통 바로 앞에서 쏟음
    hx, hy = SIM_LAYOUT[0]
    end = world.pose()
    assert math.hypot(hx - end["x"], hy - end["y"]) < 0.35       # 출발점으로 돌아옴
    assert robot.driver.state.moving is None


def test_mission_fails_when_marker_missing():
    robot = main.Robot()
    clock = VirtualClock()
    robot.driver.world.set_clock(clock)
    robot.driver.world.layout.pop(3)  # 종이 통이 없음
    robot.mission.sleep = clock.sleep

    async def run():
        robot.mission.start("paper")
        await asyncio.wait_for(robot.mission.wait(), 20)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "failed" and "못 찾았" in robot.mission.state["message"]


def test_look_around_turns_toward_marker():
    # 정면에선 안 보이고 카메라를 오른쪽(50°)으로 돌렸을 때만 보이면 → 오른쪽으로 회전 (기본은 왼쪽), 카메라는 정면으로 복귀
    robot = main.Robot()
    clock = VirtualClock()
    robot.mission.sleep = clock.sleep
    target = main.STATIONS["pet"]["marker"]
    robot.vision.markers = lambda: [Marker(target, 0.0, 0.1)] if robot.driver.state.pan == 50 else []
    turns = []
    robot.move = lambda action, speed, ms: turns.append(action)

    async def run():
        robot.mission.start("pet", dump=False, return_home=False)
        while len(turns) < 2:
            await asyncio.sleep(0)
        robot.mission.cancel()

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert turns[:2] == ["turn_right", "turn_right"]
    assert robot.driver.state.pan == 90


# ---- API ----

def test_mission_api_and_manual_override():
    with TestClient(main.app) as c:
        assert set(c.get("/api/stations").json()) >= {"home", "can", "pet", "paper"}
        seen = c.get("/api/markers").json()
        assert {m["id"] for m in seen["markers"]} == {1, 2, 3} and "pose" in seen  # 출발 자리에서 통 3개가 보임
        assert c.post("/api/mission", json={"station": "kitchen"}).status_code == 422
        assert c.post("/api/mission", json={"station": "pet"}).status_code == 202
        time.sleep(0.2)
        assert c.get("/api/mission").json()["running"] is True
        assert c.post("/api/mission", json={"station": "paper"}).status_code == 409
        s = c.post("/api/move", json={"action": "backward", "duration_ms": 100}).json()  # 수동 조종 → 임무 취소
        assert s["moving"] == "backward" and s["mission"] == "cancelled"
        m = c.get("/api/mission").json()
        assert m["running"] is False and m["message"] == "수동 조종"
