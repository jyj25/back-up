"""실패하면 비우기를 기다리지 않고 마커를 다시 찾으러 간다 (줄 따라가기: 전진한 만큼 뒤로 물러난 뒤)."""
import asyncio
import dataclasses
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.vision import Marker  # noqa: E402


def _robot(retries):
    robot = main.Robot()

    async def nosleep(s):
        await asyncio.sleep(0)

    robot.mission.sleep = nosleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)
    c = robot.mission.cfg
    c.row_mode, c.line_mode, c.dump_side, c.finish_after_dump = True, True, None, True
    c.arrive_size, c.arrive_cx, c.center_tol = 0.15, 0.3, 0.15
    c.line_advance_steps, c.fail_retries = 3, retries
    return robot


def _run(robot, find_after):
    """find_after: 전진 pulse 가 이만큼 쌓이면 목표 마커가 가운데 크게 보인다 (None 이면 끝까지 안 보임)"""
    moves = []
    orig = robot.move

    def move(action, speed, ms):
        moves.append(action)

    robot.move = move
    state = {"fwd": 0}

    async def look():
        net = moves.count("forward") - moves.count("backward")
        robot.mission.seen = [Marker(id=2, cx=0.0, size=0.2)] if find_after is not None and net >= find_after else []

    robot.mission._look = look
    async def go():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.move = orig
        robot.close()
    return moves


def test_retry_backs_up_then_searches_again_and_fails_at_the_end():
    robot = _robot(retries=1)
    moves = _run(robot, find_after=None)
    assert robot.mission.state["phase"] == "failed"
    assert moves.count("backward") == 3          # 3걸음 전진했다가 처음 자리로
    assert moves.count("forward") == 6           # 두 번 찾았다


def test_no_retry_by_default():
    robot = _robot(retries=0)
    moves = _run(robot, find_after=None)
    assert robot.mission.state["phase"] == "failed" and "backward" not in moves
