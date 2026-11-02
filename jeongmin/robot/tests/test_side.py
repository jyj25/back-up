"""카메라가 오른쪽을 보고 마커 줄이 오른쪽에 있을 때: 줄 따라 전진·후진으로 맞추고, 오른쪽으로 다가가 쏟는다."""
import asyncio
import dataclasses
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.vision import Marker  # noqa: E402


def _robot():
    robot = main.Robot()

    async def nosleep(s):
        await asyncio.sleep(0)

    robot.mission.sleep = nosleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)
    c = robot.mission.cfg
    c.row_mode, c.line_mode, c.side_camera, c.dump_side, c.finish_after_dump = True, True, True, None, True
    c.arrive_size, c.arrive_cx, c.center_tol, c.fail_retries = 0.15, 0.3, 0.15, 0
    c.side_approach = True
    return robot


def _run(robot):
    async def go():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()


def test_aligns_along_the_row_then_approaches_to_the_right_and_dumps():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    w = {"x": 0, "d": 8}               # 마커는 앞쪽 3칸에 있고, 오른쪽으로 8칸 떨어져 있다
    moves, dumps = [], []

    def markers():
        return [Marker(target, (3 - w["x"]) * 0.2, 0.6 / w["d"])]   # 앞쪽 마커는 화면 오른쪽에 보인다

    def move(action, speed, ms):
        moves.append(action)
        w["x"] += {"forward": 1, "backward": -1}.get(action, 0)
        w["d"] -= {"strafe_right": 1, "strafe_left": -1}.get(action, 0)

    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: dumps.append(len(moves))
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves[:3] == ["forward"] * 3 and set(moves[3:]) == {"strafe_right"}, moves
    assert not any(a.startswith("turn") for a in moves)
    assert dumps == [len(moves)]


def test_marker_behind_means_backward():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    w = {"x": 0, "d": 4}
    moves = []

    def markers():
        return [Marker(target, -(2 + w["x"]) * 0.2 if w["x"] > -2 else 0.0, 0.6 / w["d"])]   # 뒤쪽 마커는 화면 왼쪽

    def move(action, speed, ms):
        moves.append(action)
        w["x"] += {"forward": 1, "backward": -1}.get(action, 0)

    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert moves and set(moves) == {"backward"}, moves


def test_stops_and_dumps_as_soon_as_marker_is_in_front():
    robot = _robot()
    robot.mission.cfg.side_approach = False
    target = main.STATIONS["can"]["marker"]
    w = {"x": 0}
    moves, dumps = [], []

    def markers():
        return [Marker(target, (2 - w["x"]) * 0.2, 0.05)]       # 멀리(작게) 보여도 가운데면 바로 선다

    def move(action, speed, ms):
        moves.append(action)
        w["x"] += {"forward": 1, "backward": -1}.get(action, 0)

    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: dumps.append(len(moves))
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["forward"] * 2 and dumps == [2]                 # 옆걸음 없이 줄 따라 맞추고 쏟는다


def test_target_lost_for_a_moment_goes_back_toward_where_it_was_seen():
    robot = _robot()
    robot.mission.cfg.side_approach = False
    target = main.STATIONS["can"]["marker"]
    moves = []

    def markers():
        if len(moves) == 0:
            return [Marker(target, -0.5, 0.03)]      # 뒤쪽(화면 왼쪽)에 잠깐 보였다 → 가운데는 아니라 후진
        if len(moves) == 1:
            return []                                  # 놓침
        return [Marker(target, 0.0, 0.03)]             # 다시 보임, 가운데 → 쏟음

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["backward", "backward"], moves     # 놓쳐도 앞으로 가지 않고 본 쪽으로 돌아간다


def test_other_marker_in_view_means_step_forward_and_look_again():
    robot = _robot()
    robot.mission.cfg.side_approach = False
    target = main.STATIONS["can"]["marker"]
    other = main.STATIONS["pet"]["marker"]
    moves = []

    def markers():
        fwd = moves.count("forward")
        return [Marker(target, 0.0, 0.03)] if fwd >= 2 else [Marker(other, 0.0, 0.03)]

    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert robot.mission.state["phase"] == "done" and moves == ["forward", "forward"], (robot.mission.state, moves)


def test_drifting_away_from_the_row_is_corrected_by_strafing_back():
    robot = _robot()
    c = robot.mission.cfg
    c.side_approach, c.side_hold, c.side_hold_max = False, 0.35, 8
    target = main.STATIONS["can"]["marker"]
    other = main.STATIONS["pet"]["marker"]
    w = {"d": 6.0, "fwd": 0}
    moves = []

    def markers():
        if w["fwd"] >= 4:
            return [Marker(target, 0.0, 0.6 / 6)]
        return [Marker(other, 0.0, 0.6 / w["d"])]            # 같은 번호가 아닌 줄 마커, 보이는 크기 = 줄과의 거리

    def move(action, speed, ms):
        moves.append(action)
        if action == "forward":
            w["fwd"] += 1
            w["d"] += 1.2                                     # 걸을수록 줄에서 멀어지는 비뚤어진 길
        w["d"] -= {"strafe_right": 1.5, "strafe_left": -1.5}.get(action, 0)

    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert "strafe_right" in moves and "strafe_left" not in moves, moves


def test_camera_turns_to_scan_angle_and_pauses_before_moving():
    robot = _robot()
    c = robot.mission.cfg
    c.scan_pan, c.scan_pause_ms, c.side_approach = 90, 1500, False
    target = main.STATIONS["can"]["marker"]
    events, sleeps = [], []
    orig_sleep = robot.mission.sleep

    async def sleep(s):
        sleeps.append((s, len(events)))
        await orig_sleep(s)

    robot.mission.sleep = sleep
    robot.driver.set_servo = lambda pan, tilt: events.append(("pan", pan))
    robot.vision.markers = lambda: [Marker(target, 0.0, 0.03)]
    robot.move = lambda action, speed, ms: events.append(("move", action))
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert events[0] == ("pan", 90)                              # 카메라가 먼저 돌아간다
    assert sleeps[0] == (1.5, 1)                                 # 돌린 직후 1.5초 멈춰서 마커를 본다 (그전에 움직인 게 없다)
