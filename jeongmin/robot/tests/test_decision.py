"""확정 판정이 프레임에 덮어써져도 last_decision 으로 남는다."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402


def test_last_decision_survives_following_frames():
    robot = main.Robot()
    try:
        s = robot.sorter
        assert s.last_decision is None
        s.handle({"class": "can", "conf": 0.93, "ms": 40, "n": 1})
        for _ in range(5):                                          # 프레임이 last_verdict 를 계속 덮어쓴다
            s.handle({"class": None, "conf": 0.0, "ms": 40, "n": 1})
        assert s.last_verdict["class"] is None
        assert s.last_decision["class"] == "can" and s.last_decision["conf"] == 0.93
        assert "result" in s.last_decision                          # 출발/자동 출발 꺼짐 같은 결과 글자도 같이 있다
    finally:
        robot.close()


def test_errors_and_empty_frames_are_not_decisions():
    robot = main.Robot()
    try:
        s = robot.sorter
        s.handle({"error": "camera"})
        s.handle({"class": None, "conf": 0.0, "ms": 40, "n": 0})
        assert s.last_decision is None
    finally:
        robot.close()


def test_sort_endpoint_exposes_last_decision():
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        main.robot.sorter.handle({"class": "pet", "conf": 0.9, "ms": 40, "n": 1})
        main.robot.sorter.handle({"class": None, "conf": 0.0, "ms": 40, "n": 1})
        j = c.get("/api/sort").json()
        assert j["last_verdict"]["class"] is None
        assert j["last_decision"]["class"] == "pet"
