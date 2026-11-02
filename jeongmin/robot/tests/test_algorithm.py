"""정리한 알고리즘 시험: 샤오 판정 → 라벨 번호 블록 찾기 → 앞에서 왼쪽 90° → 쏟고 끝."""
import asyncio
import dataclasses
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.sorter import EMPTY_MSG  # noqa: E402
from server.vision import CANDIDATE, Marker  # noqa: E402


class VirtualClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += s
        await asyncio.sleep(0)


def _robot():
    robot = main.Robot()
    robot.mission.sleep = VirtualClock().sleep
    robot.mission.cfg = dataclasses.replace(robot.mission.cfg)  # 시험끼리 설정이 새지 않게 복사본
    return robot


# ---- 샤오 판정: 빈 트레이면 오류 메시지, 라벨이 있으면 그 라벨의 통으로 ----

def test_empty_tray_asks_for_an_item():
    robot = _robot()
    try:
        robot.sorter.handle({"class": None, "conf": 0.0, "n": 0})
        r = robot.sorter.go_now()
        assert not r["ok"] and r["reason"] == EMPTY_MSG and r["status"] == 422
        assert robot.sorter.last_verdict["result"] == EMPTY_MSG
        robot.sorter.handle({"class": "empty", "conf": 0.99})
        assert robot.sorter.last_verdict["result"] == EMPTY_MSG
    finally:
        robot.close()


def test_go_now_sends_to_the_judged_label():
    robot = _robot()
    started = []
    robot.sorter.start = lambda station, **kw: started.append((station, kw))
    try:
        robot.sorter.handle({"class": "paper", "conf": 0.93, "n": 1})   # 자동 출발은 꺼져 있음 → 기억만
        assert started == []
        robot.sorter.handle({"class": None, "conf": 0.2, "n": 1})       # 물건이 그대로 있는 다음 프레임
        r = robot.sorter.go_now()
        assert r["ok"] and started[0][0] == "paper"
        assert started[0][1]["return_home"] == (not robot.mission.cfg.finish_after_dump)
        assert not robot.sorter.go_now()["ok"]                          # 한 번 보내면 다시 판정이 와야 함
    finally:
        robot.close()


def test_empty_after_decision_forgets_it():
    robot = _robot()
    try:
        robot.sorter.handle({"class": "can", "conf": 0.9, "n": 1})
        robot.sorter.handle({"class": None, "conf": 0.0, "n": 0})       # 치워서 빈 트레이
        assert robot.sorter.go_now()["reason"] == EMPTY_MSG
    finally:
        robot.close()


def test_low_confidence_is_not_decided():
    robot = _robot()
    try:
        robot.sorter.handle({"class": "pet", "conf": 0.4, "n": 1})
        r = robot.sorter.go_now()
        assert not r["ok"] and "확인하는 중" in r["reason"]
    finally:
        robot.close()


# ---- 이미 식별된 번호 아닌 블록은 미식별 후보에서 제외 ----

def test_identified_blocks_are_excluded_from_unknowns():
    robot = _robot()
    try:
        m = robot.mission
        target = main.STATIONS["can"]["marker"]
        other = main.STATIONS["pet"]["marker"]
        sightings = [
            {"id": other, "bearing": 0.0, "size": 0.2},        # 번호를 읽은 다른 통
            {"id": CANDIDATE, "bearing": 5.0, "size": 0.05},   # 같은 블록을 멀리서 본 후보 → 제외
            {"id": CANDIDATE, "bearing": 120.0, "size": 0.04}, # 다른 방향의 미식별 블록 → 남김
        ]
        assert m._unknowns(sightings, target, []) == [120.0]
        assert m._unknowns(sightings, target, [120.0]) == []   # 이미 가 본 방향도 제외
    finally:
        robot.close()


# ---- 도착하면 왼쪽 90° → 쏟고 끝 ----

def test_arrive_turn_left_dump_and_finish():
    robot = _robot()
    target = main.STATIONS["can"]["marker"]
    robot.vision.markers = lambda: [Marker(target, 0.0, 0.5)]            # 바로 앞에 있음
    robot.mission.cfg.dump_side = "right"
    robot.mission.cfg.dock_steps = 0
    robot.mission.cfg.finish_after_dump = True
    moves, dumps = [], []
    robot.move = lambda action, speed, ms: moves.append(action)
    robot.driver.dump = lambda: dumps.append(len(moves))

    async def run():
        robot.mission.start("can", dump=True, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "done", robot.mission.state
    assert moves == ["turn_left"], moves          # 왼쪽 90° 한 번뿐 (되돌아 돌거나 뒤로 빠지지 않음)
    assert dumps == [1]                           # 그 뒤에 쏟음


# ---- 못 찾으면 처음부터 다시 둘러본다 ----

def test_rescans_when_target_not_found():
    robot = _robot()
    robot.mission.cfg.rescans = 1
    robot.vision.markers = lambda: []
    turns = []
    robot.move = lambda action, speed, ms: turns.append(robot.mission._turn_deg(action, ms - 300))

    async def run():
        robot.mission.start("can", dump=False, return_home=False)
        await asyncio.wait_for(robot.mission.wait(), 5)

    try:
        asyncio.run(run())
    finally:
        robot.close()
    assert robot.mission.state["phase"] == "failed"
    assert 720 <= sum(turns) < 720 + 90           # 한 바퀴 + 다시 한 바퀴
