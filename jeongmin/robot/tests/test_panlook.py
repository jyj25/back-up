"""pan_look: 일직선 전진·후진만. 멈춰서 카메라를 오른쪽으로 돌려 확인하고, 아니면 정면으로 돌려 한 걸음 전진한다."""
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
    c.pan_look, c.row_mode, c.dump_side, c.finish_after_dump = True, True, None, True
    c.travel_pan, c.scan_pan, c.scan_pause_ms, c.center_tol, c.fail_retries = 135, 90, 1000, 0.15, 0
    c.line_advance_steps = 6
    c.pan_center = True
    return robot


def _run(robot):
    async def go():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(go())
    finally:
        robot.close()


def test_looks_right_at_each_stop_skips_other_markers_and_dumps_at_the_target():
    robot = _robot()
    target, other = main.STATIONS["can"]["marker"], main.STATIONS["pet"]["marker"]
    ev, dumps = [], []

    def markers():
        fwd = sum(1 for e in ev if e == ("move", "forward"))
        return [Marker(other, 0.0, 0.1)] if fwd < 3 else [Marker(target, 0.0, 0.1)]

    robot.driver.set_servo = lambda pan, tilt: ev.append(("pan", pan))
    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: ev.append(("move", action))
    robot.driver.dump = lambda *a: dumps.append(1)
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    moves = [e[1] for e in ev if e[0] == "move"]
    assert moves == ["forward"] * 3 and dumps == [1]
    assert ev[0] == ("pan", 90) and ("pan", 135) in ev
    for i, e in enumerate(ev):
        if e == ("move", "forward"):
            assert ev[i - 1] == ("pan", 135)


def test_aligns_with_forward_and_backward_only():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    w = {"x": 0}
    moves = []

    def markers():
        return [Marker(target, (3 - w["x"]) * 0.2, 0.1)]

    def move(action, speed, ms):
        moves.append(action)
        w["x"] += {"forward": 1, "backward": -1}.get(action, 0)

    robot.driver.set_servo = lambda pan, tilt: None
    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert robot.mission.state["phase"] == "done" and set(moves) == {"forward"}, (robot.mission.state, moves)


def test_gives_up_after_sweeping_forward_then_backward_without_turning():
    robot = _robot()
    c = robot.mission.cfg
    c.fail_retries, c.pan_back_margin = 1, 2          # 앞으로 6걸음, 그다음 후진해서 출발점 뒤 2걸음까지
    moves = []
    robot.driver.set_servo = lambda pan, tilt: None
    robot.vision.markers = lambda: []
    robot.move = lambda action, speed, ms: moves.append(action)
    _run(robot)
    assert robot.mission.state["phase"] == "failed"
    assert moves == ["forward"] * 6 + ["backward"] * 8, moves     # 6 앞 → 되돌아 6+2 뒤. 회전·옆걸음 없음


def test_marker_found_on_the_way_back_is_dumped_there():
    robot = _robot()
    c = robot.mission.cfg
    c.fail_retries = 1
    target = main.STATIONS["can"]["marker"]
    net, moves, dumps = {"x": 0}, [], []

    def markers():
        return [Marker(target, 0.0, 0.05)] if net["x"] == 2 and moves.count("backward") > 0 else []   # 되돌아오다 2칸 지점에서 보인다

    def move(action, speed, ms):
        moves.append(action)
        net["x"] += {"forward": 1, "backward": -1}.get(action, 0)

    robot.driver.set_servo = lambda pan, tilt: None
    robot.vision.markers = markers
    robot.move = move
    robot.driver.dump = lambda *a: dumps.append(1)
    _run(robot)
    assert robot.mission.state["phase"] == "done" and dumps == [1], robot.mission.state
    assert not any(a.startswith(("turn", "strafe")) for a in moves)


def test_stops_and_dumps_the_moment_the_target_is_seen_when_not_centering():
    robot = _robot()
    robot.mission.cfg.pan_center = False
    target, other = main.STATIONS["can"]["marker"], main.STATIONS["pet"]["marker"]
    moves, dumps = [], []

    def markers():
        fwd = moves.count("forward")
        return [Marker(other, -0.3, 0.05)] if fwd < 2 else [Marker(target, 0.8, 0.05)]   # 가운데가 아니어도

    robot.driver.set_servo = lambda pan, tilt: None
    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda *a: dumps.append(len(moves))
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["forward", "forward"] and dumps == [2]       # 다른 마커는 지나치고, 목표가 보이는 순간 멈춰 쏟는다


def test_camera_stays_on_the_marker_row_when_travel_and_scan_pan_are_equal():
    robot = _robot()
    c = robot.mission.cfg
    c.travel_pan = c.scan_pan = 15
    target, other = main.STATIONS["can"]["marker"], main.STATIONS["pet"]["marker"]
    ev = []

    def markers():
        fwd = sum(1 for e in ev if e == ("move", "forward"))
        return [Marker(other, 0.0, 0.1)] if fwd < 4 else [Marker(target, 0.0, 0.1)]

    robot.driver.set_servo = lambda pan, tilt: ev.append(("pan", pan))
    robot.vision.markers = markers
    robot.move = lambda action, speed, ms: ev.append(("move", action))
    robot.driver.dump = lambda *a: None
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert [e for e in ev if e[0] == "pan"] == [("pan", 15)]          # 카메라는 처음 한 번만 돌리고 그 뒤로는 안 움직인다
    assert [e[1] for e in ev if e[0] == "move"] == ["forward"] * 4


def test_stops_once_to_judge_each_new_marker_that_is_not_the_target():
    robot = _robot()
    c = robot.mission.cfg
    c.pan_judge_ms = 1500
    target, other = main.STATIONS["can"]["marker"], main.STATIONS["pet"]["marker"]
    moves, sleeps = [], []
    orig = robot.mission.sleep

    async def sleep(s):
        sleeps.append(s)
        await orig(s)

    robot.mission.sleep = sleep
    robot.driver.set_servo = lambda pan, tilt: None
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda *a: None

    def markers():
        fwd = moves.count("forward")
        return [Marker(other, 0.0, 0.1)] if 1 <= fwd <= 3 else ([Marker(target, 0.0, 0.1)] if fwd >= 4 else [])   # 같은 마커가 3번 연속 보인다

    robot.vision.markers = markers
    _run(robot)
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert sleeps.count(1.5) == 1, sleeps                        # 같은 마커로는 한 번만 멈춰서 판단


def test_blocked_ahead_is_treated_as_end_of_row_and_sweeps_backward():
    from server.navigator import NavError

    robot = _robot()
    robot.mission.cfg.fail_retries = 1
    target = main.STATIONS["can"]["marker"]
    moves, dumps = [], []

    async def pulse(action, speed, ms):
        if action == "forward" and moves.count("forward") >= 3:
            raise NavError("앞에 장애물이 있어 멈췄습니다")
        moves.append(action)

    robot.mission._pulse = pulse
    robot.driver.set_servo = lambda pan, tilt: None
    robot.vision.markers = lambda: [Marker(target, 0.0, 0.05)] if moves.count("backward") >= 2 else []
    robot.driver.dump = lambda *a: dumps.append(1)
    _run(robot)
    assert robot.mission.state["phase"] == "done" and dumps == [1], robot.mission.state
    assert moves == ["forward"] * 3 + ["backward"] * 2, moves
