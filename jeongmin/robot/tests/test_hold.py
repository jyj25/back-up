"""마커 줄과의 거리 유지: 크기가 줄면 줄 쪽(오른쪽)으로, 커지면 반대로 아주 조금 옆걸음."""
import asyncio
import dataclasses
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.vision import Marker  # noqa: E402


def _run_hold(sizes):
    robot = main.Robot()

    async def nosleep(s):
        await asyncio.sleep(0)

    robot.mission.sleep = nosleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)
    c = robot.mission.cfg
    c.pan_look, c.row_mode, c.dump_side, c.finish_after_dump = True, True, None, True
    c.travel_pan, c.scan_pan, c.scan_pause_ms, c.fail_retries, c.line_advance_steps = 90, 90, 0, 0, 6
    c.pan_center, c.hold_row, c.return_to_start = True, True, False
    target, other = main.STATIONS["can"]["marker"], main.STATIONS["pet"]["marker"]
    moves = []

    def markers():
        fwd = sum(1 for m in moves if m == "forward")
        sz = sizes.get(fwd, sizes["last"])
        return [Marker(target, 0.0, 0.1)] if fwd >= 4 else [Marker(other, 0.0, sz)]

    robot.driver.set_servo = lambda pan, tilt: None
    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda *a: None

    async def go():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()
    return moves


def test_moving_away_from_the_row_strafes_toward_it():
    moves = _run_hold({0: 0.10, "last": 0.06})   # 줄에서 멀어져 마커가 작아 보임
    assert "strafe_right" in moves and "strafe_left" not in moves, moves


def test_getting_too_close_strafes_away():
    moves = _run_hold({0: 0.10, "last": 0.15})
    assert "strafe_left" in moves and "strafe_right" not in moves, moves


def test_constant_distance_no_strafe():
    moves = _run_hold({0: 0.10, "last": 0.10})
    assert not any(m.startswith("strafe") for m in moves), moves
