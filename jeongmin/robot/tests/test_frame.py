"""파이 판정 프레임 줄: 상태·확률·위치·연속 횟수."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.judge import Detector, PiJudge  # noqa: E402
from server.sorter import EMPTY_MSG  # noqa: E402


def _judge():
    j = PiJudge(cam=None, model_path="/none", on_line=lambda line: None)
    j.detector = Detector()  # 이 시험은 프레임 줄의 모양을 보는 것이라 예전 방식(같은 결과 3번 연속) 판정기를 쓴다
    return j


def box(label, conf=0.95, x=16, y=24):
    return (label, conf, x, y, 8, 8)


def test_state_follows_the_detector():
    j = _judge()
    assert j.frame_obj([], 0, 40)["state"] == "ready"                   # 빈 트레이
    assert j.frame_obj([box("pet")], 1, 40)["state"] == "detecting"     # 물체 있음, 아직 확정 전
    for i in range(3):                                                   # 같은 결과 3번 → 확정
        j.detector.update([box("pet")], i * 100)
    f = j.frame_obj([box("pet")], 1, 40)
    assert j.detector.waiting and f["state"] == "wait_empty"            # 확정 뒤엔 '비우기 기다림' (계속 '인식 중'이 아님)


def test_probs_box_and_streak():
    j = _judge()
    j.detector.update([box("can", 0.9)], 0)
    f = j.frame_obj([box("can", 0.9, 16, 24), box("can", 0.7, 24, 24), box("pet", 0.65, 70, 70)], 2, 41)
    assert f["event"] == "frame" and f["class"] is None and f["n"] == 2
    assert f["probs"]["can"] == 0.9 and f["probs"]["pet"] == 0.65 and f["probs"]["empty"] == 0.0
    assert f["streak"] == 1
    x, y, w, h = f["box"]                                                # 가장 확신하는 종류(can) 두 칸을 감싼다
    assert (x, y) == (round(16 / 96, 3), round(24 / 96, 3)) and w == round(16 / 96, 3) and h == round(8 / 96, 3)
    assert j.frame_obj([], 0, 40)["probs"]["empty"] == 1.0 and j.frame_obj([], 0, 40)["box"] is None


def test_empty_frame_event_still_asks_for_an_item():
    robot = main.Robot()
    try:
        robot.sorter.handle({"event": "frame", "class": None, "conf": 0.0, "ms": 40, "n": 0, "state": "ready", "probs": {"empty": 1.0}})
        assert robot.sorter.last_verdict["result"] == EMPTY_MSG
        assert robot.sorter.go_now()["reason"] == EMPTY_MSG
    finally:
        robot.close()


def test_frame_event_does_not_break_decision_memory():
    robot = main.Robot()
    try:
        s = robot.sorter
        s.handle({"class": "pet", "conf": 0.98, "ms": 40, "n": 1})
        s.handle({"event": "frame", "class": None, "conf": 0.0, "ms": 40, "n": 1, "state": "wait_empty", "probs": {"pet": 0.97, "empty": 0.0}})
        assert s.last_decision["class"] == "pet"
        assert s._decided is not None and s._decided[0] == "pet"   # 확정 기억은 물체가 있는 프레임에 지워지지 않는다 (빈 트레이일 때만 지움)
    finally:
        robot.close()
