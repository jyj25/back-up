"""쏟은 뒤 샤오가 '비어있음'을 못 보면 2배속으로 다시 쏟는다."""
import asyncio
import os
import time

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402


class VirtualClock:
    async def sleep(self, s: float) -> None:
        await asyncio.sleep(0)


def _robot():
    robot = main.Robot()
    robot.mission.sleep = VirtualClock().sleep
    return robot


def test_dump_again_at_double_speed_until_empty():
    robot = _robot()
    m = robot.mission
    speeds = []
    robot.driver.dump = lambda speed=1.0: speeds.append(speed)
    m._board_judges = lambda: True
    results = iter([False, True])        # 첫 쏟기 뒤엔 물건이 보이고, 2배속으로 다시 쏟으니 비었음

    async def fake_wait(sorter, timeout=15.0):
        return next(results)

    m._wait_empty = fake_wait
    try:
        asyncio.run(m._dump_with_tray("캔"))
    finally:
        robot.close()
    assert speeds == [1.0, 2.0]
    assert not m.state.get("tray_left")


def test_gives_up_after_two_fast_retries():
    robot = _robot()
    m = robot.mission
    speeds = []
    robot.driver.dump = lambda speed=1.0: speeds.append(speed)
    m._board_judges = lambda: True

    async def never_empty(sorter, timeout=15.0):
        return False

    m._wait_empty = never_empty
    try:
        asyncio.run(m._dump_with_tray("캔"))
    finally:
        robot.close()
    assert speeds == [1.0, 2.0, 2.0]     # 처음 1번 + 2배속 2번
    assert m.state["tray_left"] is True
    assert "비지 않음" in m.state["message"]


def test_no_retry_when_already_empty():
    robot = _robot()
    m = robot.mission
    speeds = []
    robot.driver.dump = lambda speed=1.0: speeds.append(speed)
    m._board_judges = lambda: True

    async def empty(sorter, timeout=15.0):
        return True

    m._wait_empty = empty
    try:
        asyncio.run(m._dump_with_tray("캔"))
    finally:
        robot.close()
    assert speeds == [1.0]


def test_empty_after_uses_the_time_the_photo_was_taken():
    robot = _robot()
    s = robot.sorter
    try:
        t = time.monotonic() - 1.0
        assert s.empty_after(t) is None                                  # 아직 프레임 없음
        s.handle({"class": None, "conf": 0.0, "ms": 5000, "n": 0})       # 5초 전에 찍은 사진 → t 보다 이전이라 안 믿음
        assert s.empty_after(t) is None
        s.handle({"class": None, "conf": 0.0, "ms": 100, "n": 2})        # 쏟은 뒤에 찍은 사진에 물건이 보임
        assert s.empty_after(t) is False
        s.handle({"class": None, "conf": 0.0, "ms": 100, "n": 0})        # 비었음
        assert s.empty_after(t) is True
    finally:
        robot.close()


def test_driver_dump_accepts_speed():
    robot = _robot()
    try:
        robot.driver.dump()
        robot.driver.dump(2.0)
        assert robot.driver.state.history[-2:] == ["dump", "dump x2"]
    finally:
        robot.close()
