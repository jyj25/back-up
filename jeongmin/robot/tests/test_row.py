"""줄 따라가기 모드: 회전·주변 탐색 없이 전진·후진·옆 이동만으로 목표 마커 앞에 서서 쏟는다."""
import asyncio
import dataclasses
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.vision import Marker  # noqa: E402


class VirtualClock:
    async def sleep(self, s: float) -> None:
        await asyncio.sleep(0)


def _robot():
    robot = main.Robot()
    robot.mission.sleep = VirtualClock().sleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)
    c = robot.mission.cfg
    c.row_mode, c.line_mode, c.dump_side, c.finish_after_dump = True, True, None, True
    c.arrive_size, c.arrive_cx, c.center_tol = 0.15, 0.3, 0.15
    return robot


def _run(robot):
    async def go():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()


def test_strafes_to_center_then_goes_forward_and_dumps_without_turning():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    moves, dumps = [], []
    st = {"cx": 0.6, "size": 0.05}

    def markers():
        return [Marker(target, st["cx"], st["size"])]

    def move(action, speed, ms):
        moves.append(action)
        if action == "strafe_right":
            st["cx"] = 0.0                      # 옆으로 가서 가운데로
        if action == "forward":
            st["size"] += 0.06                  # 전진할수록 크게 보임

    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: dumps.append(len(moves))
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves[0] == "strafe_right" and set(moves[1:]) == {"forward"}, moves
    assert not any(a.startswith("turn") for a in moves)                   # 회전 없음
    assert robot.driver.state.pan == 90                                   # 카메라 좌우 둘러보기도 없음
    assert dumps == [len(moves)]                                          # 도착한 자리에서 바로 쏟음


def test_moves_forward_when_target_is_not_visible_and_never_turns():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    moves = []

    def markers():
        fwd = moves.count("forward")
        if fwd >= 5:
            return [Marker(target, 0.0, 0.2)]
        if fwd >= 3:
            return [Marker(main.STATIONS["pet"]["marker"], -0.5, 0.05)]    # 다른 번호만 멀리 보임
        return []

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert set(moves) == {"forward"} and len(moves) == 5, moves
    assert robot.driver.state.pan == 90


def test_backs_up_when_too_close():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    moves = []
    st = {"size": 0.5}                                                    # arrive_size 0.15 × 1.8 = 0.27 보다 큼 → 너무 가까움

    def move(action, speed, ms):
        moves.append(action)
        if action == "backward":
            st["size"] = 0.2

    robot.vision.markers = lambda: [Marker(target, 0.0, st["size"])]
    robot.move = move
    _run(robot)
    assert moves[0] == "backward"                                         # 후진으로 거리를 맞춘다
    assert robot.mission.state["phase"] == "done", robot.mission.state


def test_stops_in_front_of_the_row_when_target_missing():
    robot = _robot()
    moves = []
    robot.vision.markers = lambda: [Marker(main.STATIONS["pet"]["marker"], 0.2, 0.3)]   # 줄 바로 앞인데 목표가 아님
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    st = robot.mission.state
    assert st["phase"] == "failed" and "바로 앞" in st["message"], st
    assert moves == []                                                    # 더 가지 않는다


def test_gives_up_after_the_step_limit_without_spinning():
    robot = _robot()
    robot.mission.cfg.line_advance_steps = 3
    robot.vision.markers = lambda: []
    moves = []
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "failed" and moves == ["forward"] * 3, moves


def test_passes_by_a_marker_that_is_off_to_the_side():
    # 마커 사이에는 쓰레기가 떨어질 공간이 있다: 옆에 비켜 있는 다른 번호 마커가 크게 보여도 멈추지 않고 지나간다
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    moves = []

    def markers():
        fwd = moves.count("forward")
        if fwd >= 4:
            return [Marker(target, 0.0, 0.2)]
        return [Marker(main.STATIONS["pet"]["marker"], 0.8, 0.3)]          # 오른쪽 옆에 크게 보이는 다른 번호

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["forward"] * 4, moves
