"""마커 일렬 모드: 마커가 안 보이면 앞으로 전진하며 스캔하고, 맞는 번호가 보이면 거기서 쏟는다."""
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
    robot.mission.cfg.line_mode = True
    robot.mission.cfg.dump_side = None
    robot.mission.cfg.finish_after_dump = True
    return robot


def _run(robot):
    async def go():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()


def test_advances_forward_until_the_target_appears_then_dumps():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    moves, dumps = [], []

    def markers():
        # 세 걸음 전진하면 마커 줄이 보이고(다른 번호만 작게), 다섯 걸음에 목표가 크게 보인다
        fwd = moves.count("forward")
        if fwd >= 5:
            return [Marker(target, 0.0, 0.4)]
        if fwd >= 3:
            return [Marker(main.STATIONS["pet"]["marker"], -0.5, 0.05)]
        return []

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda *a: dumps.append(len(moves))
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert set(moves) == {"forward"} and len(moves) == 5, moves        # 몸으로 돌지 않고 전진만
    assert dumps == [5]                                                  # 목표가 보여 도착한 뒤 쏟음


def test_gives_up_after_the_step_limit_without_spinning():
    robot = _robot()
    robot.mission.cfg.line_advance_steps = 4
    robot.vision.markers = lambda: []
    moves = []
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    st = robot.mission.state
    assert st["phase"] == "failed" and "일렬" in st["message"], st
    assert moves == ["forward"] * 4, moves                               # 정해진 걸음만 가고 멈춤, 회전 없음


def test_stops_when_close_to_the_line_but_target_is_missing():
    robot = _robot()
    other = main.STATIONS["pet"]["marker"]
    robot.vision.markers = lambda: [Marker(other, 0.2, 0.3)]            # 줄 바로 앞인데 목표가 아님
    moves = []
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    st = robot.mission.state
    assert st["phase"] == "failed" and "바로 앞" in st["message"], st
    assert "forward" not in moves                                        # 더 전진하지 않는다
