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


def test_decide_far_candidates_get_closer():
    from server.vision import CANDIDATE
    far = [Marker(CANDIDATE, 0.6, 0.03), Marker(CANDIDATE, 0.4, 0.03)]       # 번호 못 읽는 네모 둘, 오른쪽
    s = decide(far, 1, 200, CFG)
    assert (s.phase, s.action) == ("closer", "turn_right")
    centered = [Marker(CANDIDATE, -0.1, 0.03), Marker(CANDIDATE, 0.1, 0.03)]
    assert decide(centered, 1, 200, CFG).action == "forward"
    assert decide(centered + [Marker(1, 0.5, 0.1)], 1, 200, CFG).phase == "align"  # 목표가 읽히면 목표 우선


def test_decide_align_approach_arrive():
    s = decide([Marker(1, 0.6, 0.1)], 1, 200, CFG)
    assert (s.phase, s.action) == ("align", "turn_right") and CFG.turn_dead_ms < s.ms < CFG.turn90_ms
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
    found = [m for m in detect(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)) if m.id >= 0]
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
    assert sorted(m.id for m in detect(frame, make_detector(conf["marker_dict"])) if m.id >= 0) == [2, 4]
    assert all(m.id < 0 for m in detect(frame))  # 기본(4x4) 사전으로는 번호를 못 읽는다 (후보 네모일 뿐)


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
        while len(turns) < 1:
            await asyncio.sleep(0)
        robot.mission.cancel()

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert turns[0] == "turn_right"            # 찾은 쪽으로 한 번만 회전
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


def test_marker_lost_when_close_counts_as_arrived():
    # 크게 보이던 마커가 한 걸음 뒤 사라짐 → 화면 아래로 빠진 것 → 도착 (둘러보지 않음)
    robot = main.Robot()
    clock = VirtualClock()
    robot.mission.sleep = clock.sleep
    target = main.STATIONS["can"]["marker"]
    big = robot.mission.cfg.arrive_size * 0.8
    frames = iter([[Marker(target, 0.0, big)]])
    robot.vision.markers = lambda: next(frames, [])
    moves = []
    robot.move = lambda action, speed, ms: moves.append(action)

    async def run():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "done"
    assert moves == ["forward"] and robot.driver.state.pan == 90


def test_dock_right_side_before_dump():
    # 오른쪽으로 쏟는 트레이: 카메라 오른쪽(0°) → 왼쪽으로 약 90° → 옆 화면에서 마커가 오른쪽에 있으면 보정 → 오른쪽 옆걸음
    robot = main.Robot()
    clock = VirtualClock()
    robot.mission.sleep = clock.sleep
    robot.mission.cfg.dump_side = "right"
    target = main.STATIONS["can"]["marker"]
    st = {"right": 0, "strafes": 0}
    log = []

    def markers():
        if robot.driver.state.pan != 0:
            return []
        cx = 0.5 if st["right"] == 0 else 0.0   # 90° 돌고 나면 조금 오른쪽 → 한 번 보정
        return [Marker(target, cx, 0.2 + 0.1 * st["strafes"])]

    def move(action, speed, ms):
        log.append(action)
        st["right"] += action == "turn_right"
        st["strafes"] += action == "strafe_right"

    robot.vision.markers = markers
    robot.move = move

    async def run():
        assert await robot.mission._dock_side(robot.mission.stations["can"]) == 2  # 0.2 → 0.3 → 0.4 (≥ 0.35)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert log == ["turn_left", "turn_right", "strafe_right", "strafe_right"]
    assert robot.driver.state.pan == 0


def test_dock_without_marker_still_dumps():
    # 옆 화면에 마커가 안 보여도 실패하지 않고: 약 90° 돌고 → 쏟고 → 되돌아 회전 → 출발점
    robot = main.Robot()
    clock = VirtualClock()
    robot.mission.sleep = clock.sleep
    robot.mission.cfg.dump_side = "right"
    target = main.STATIONS["can"]["marker"]
    robot.vision.markers = lambda: [Marker(target, 0.0, 0.4)] if robot.driver.state.pan == 90 else []
    log = []
    robot.move = lambda action, speed, ms: log.append(action)
    robot.driver.dump = lambda: log.append("dump")

    async def run():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert log == ["turn_left", "dump", "turn_right"]  # 옆걸음을 안 했으니 빠질 것도 없음
    assert robot.driver.state.pan == 90


def test_mission_walks_to_far_candidates_then_target():
    # 처음엔 번호 못 읽는 네모만 보임 → 앞으로 → 가까워지면 목표 번호가 읽혀 도착
    from server.vision import CANDIDATE
    robot = main.Robot()
    clock = VirtualClock()
    robot.mission.sleep = clock.sleep
    target = main.STATIONS["can"]["marker"]
    st = {"fwd": 0}
    def markers():
        if st["fwd"] < 2:
            return [Marker(CANDIDATE, 0.0, 0.03)]
        return [Marker(target, 0.0, 0.4)]
    def move(action, speed, ms):
        st["fwd"] += action == "forward"
    robot.vision.markers = markers
    robot.move = move

    async def run():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert st["fwd"] == 2


def _bare_mission():
    robot = main.Robot()
    clock = VirtualClock()
    robot.mission.sleep = clock.sleep
    return robot


def test_nothing_around_turns_once_then_stops():
    robot = _bare_mission()
    robot.vision.markers = lambda: []
    turns = []
    robot.move = lambda action, speed, ms: turns.append(robot.mission._turn_deg(action, ms - 300))  # move 에는 자동 정지 여유 300ms 가 붙는다

    async def run():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "failed" and "한 바퀴" in robot.mission.state["message"]
    assert 360 <= sum(turns) < 360 + 90                     # 딱 한 바퀴만


def test_scan_then_visit_unknown_block():
    # 왼쪽 약 90° 에 번호를 못 읽는 블록 → 한 바퀴 기록 → 그쪽으로 돌아 다가감 → 번호가 읽히면 목표
    from server.vision import CANDIDATE
    robot = _bare_mission()
    m = robot.mission
    target = main.STATIONS["can"]["marker"]
    st = {"fwd": 0}

    def markers():
        if robot.driver.state.pan != 90:
            return []
        rel = (90 - m.heading + 180) % 360 - 180            # 블록 방향 − 지금 방향 (+ = 왼쪽)
        if abs(rel) > 25:
            return []
        cx = round(-rel / m.cfg.half_fov_deg, 3)
        return [Marker(target, cx, 0.4)] if st["fwd"] >= 2 else [Marker(CANDIDATE, cx, 0.03)]

    def move(action, speed, ms):
        st["fwd"] += action == "forward"

    robot.vision.markers = markers
    robot.move = move

    async def run():
        m.start("can", dump=False, return_home=False)
        await asyncio.wait_for(m.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert m.state["phase"] == "done", m.state
    assert st["fwd"] == 2
