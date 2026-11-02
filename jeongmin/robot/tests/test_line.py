"""마커 일렬 모드: 몸으로 돌며 찾지 않는다."""
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


def _robot(line=True):
    robot = main.Robot()
    robot.mission.sleep = VirtualClock().sleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)  # 시험끼리 설정이 새지 않게 복사본
    robot.mission.cfg.line_mode = line
    return robot


def _run(robot):
    async def go():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()


def test_line_mode_does_not_spin_when_marker_missing():
    robot = _robot(line=True)
    robot.vision.markers = lambda: []
    moves = []
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    st = robot.mission.state
    assert st["phase"] == "failed" and "일렬" in st["message"] and "카메라" in st["message"], st
    assert not any(a.startswith("turn") for a in moves), moves      # 몸으로 돌지 않는다 (앞으로 전진하며 찾기만 한다)


def test_line_mode_still_finds_target_with_camera_look_around():
    robot = _robot(line=True)
    target = main.STATIONS["can"]["marker"]

    moves = []

    def markers():
        # 처음엔 카메라를 왼쪽(pan 130)으로 돌렸을 때만 목표가 보인다. 그쪽으로 몸을 돌리고 나면 정면에서도 보인다
        seen_now = robot.driver.state.pan == 130 or "turn_left" in moves
        return [Marker(target, 0.0, 0.4)] if seen_now else []

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["turn_left"], moves                              # 카메라로 찾고 한 번만 돈 뒤 접근 (한 바퀴 돌지 않음)


def test_without_line_mode_spins_to_search():
    robot = _robot(line=False)
    robot.vision.markers = lambda: []
    turns = []
    robot.move = lambda action, speed, ms: turns.append(action)
    _run(robot)
    assert any(a.startswith("turn") for a in turns)                  # 기존 방식은 몸으로 돌며 찾는다
