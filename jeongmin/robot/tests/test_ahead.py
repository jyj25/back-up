"""앞에 마커 후보가 보이면 돌아보기 전에 먼저 그쪽으로 다가간다."""
import asyncio
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.vision import CANDIDATE, Marker  # noqa: E402


class VirtualClock:
    async def sleep(self, s: float) -> None:
        await asyncio.sleep(0)


def _robot():
    robot = main.Robot()
    robot.mission.sleep = VirtualClock().sleep
    return robot


def _run(robot):
    async def go():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()


def test_candidate_ahead_is_approached_before_looking_around():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    moves, pans = [], []

    def markers():
        pans.append(robot.driver.state.pan)
        fwd = moves.count("forward")
        # 정면에 멀리 있는 네모 → 두 걸음 다가가면 번호가 읽히고 목표
        return [Marker(target, 0.0, 0.4)] if fwd >= 2 else [Marker(CANDIDATE, 0.0, 0.03)]

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["forward", "forward"], moves     # 한 바퀴 돌거나 카메라를 둘러보지 않고 바로 다가감
    assert set(pans) == {90}                           # 카메라 좌우 둘러보기(look_around)도 안 함


def test_candidate_ahead_that_is_another_block_falls_back_to_search():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    other = main.STATIONS["pet"]["marker"]
    moves = []

    def markers():
        fwd = moves.count("forward")
        # 앞의 네모는 다가가 보니 다른 번호(페트) → 목표가 아님. 목표는 한 바퀴 돌아야 보이는 왼쪽 90°
        if fwd >= 2:
            ang = (90 - robot.mission.heading + 180) % 360 - 180
            if abs(ang) < 25:
                return [Marker(target, round(-ang / robot.mission.cfg.half_fov_deg, 3), 0.4)]
            return [Marker(other, 0.0, 0.2)] if abs(robot.mission.heading) < 20 else []
        return [Marker(CANDIDATE, 0.0, 0.03)]

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves[:2] == ["forward", "forward"]         # 먼저 앞의 후보로 다가가 번호를 읽고
    assert "turn_left" in moves                         # 목표가 아니었으니 그다음에 돌아서 찾는다
