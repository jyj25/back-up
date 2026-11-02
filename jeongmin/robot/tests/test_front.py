"""마커를 확인(가운데 정렬)하고 마커 앞에서 왼쪽 90° 없이 바로 쏟는다."""
import asyncio
import dataclasses
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.navigator import NavConfig, decide  # noqa: E402
from server.vision import Marker  # noqa: E402


class VirtualClock:
    async def sleep(self, s: float) -> None:
        await asyncio.sleep(0)


def test_big_but_off_center_marker_is_aligned_before_arriving():
    cfg = NavConfig(arrive_size=0.15, arrive_cx=0.3)
    target = 2
    # 크게 보여도(0.2 ≥ 0.15) 가운데에서 많이 벗어나면 먼저 정렬한다
    s = decide([Marker(target, 0.6, 0.2)], target, 0.0, cfg)
    assert s.phase == "align" and s.action == "turn_right"
    # 가운데로 맞춰지면 도착
    assert decide([Marker(target, 0.1, 0.2)], target, 0.0, cfg).phase == "arrived"
    # 가운데여도 작으면(멀면) 계속 다가간다
    assert decide([Marker(target, 0.0, 0.05)], target, 0.0, cfg).phase == "approach"


def test_default_config_still_arrives_regardless_of_position():
    cfg = NavConfig(arrive_size=0.15)    # arrive_cx 기본 1.0 → 이전과 같음
    assert decide([Marker(2, 0.9, 0.2)], 2, 0.0, cfg).phase == "arrived"


def test_dumps_in_front_of_marker_without_turning():
    robot = main.Robot()
    robot.mission.sleep = VirtualClock().sleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)  # 시험끼리 설정이 새지 않게 복사본
    cfg = robot.mission.cfg
    cfg.dump_side, cfg.finish_after_dump, cfg.arrive_cx = None, True, 0.3
    target = main.STATIONS["can"]["marker"]
    moves, dumps = [], []
    # 마커가 오른쪽(cx 0.5)에 크게 보임 → 정렬(오른쪽으로 조금 돔) → 가운데에 오면 도착 → 바로 쏟기
    state = {"cx": 0.5}

    def markers():
        return [Marker(target, state["cx"], 0.4)]

    def move(action, speed, ms):
        moves.append(action)
        if action == "turn_right":
            state["cx"] = 0.0

    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: dumps.append(len(moves))

    async def go():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["turn_right"], moves          # 정렬 한 번뿐, 왼쪽 90° 도는 단계 없음
    assert dumps == [1]                            # 정렬이 끝난 뒤 바로 쏟음
