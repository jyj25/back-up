"""모델이 아무것도 못 찾았는데 빈 트레이 기준 사진과 다르면 종이로 본다."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server.judge import Detector, PiJudge  # noqa: E402


def _judge(area):
    j = PiJudge.__new__(PiJudge)
    j.detector = Detector()
    j.presence, j.presence_min, j.fallback = (lambda img: area), 0.02, False
    return j


def test_no_detection_but_tray_differs_becomes_paper():
    j = _judge(0.2)
    dets = j.apply_presence([], object())
    assert [d[0] for d in dets] == ["paper"] and dets[0][1] >= 0.8 and j.fallback


def test_no_detection_and_same_as_empty_tray_stays_empty():
    j = _judge(0.005)
    assert j.apply_presence([], object()) == [] and not j.fallback


def test_model_detection_is_kept_when_the_tray_differs_from_empty():
    j = _judge(0.9)
    det = [("can", 0.95, 10, 10, 20, 20)]
    assert j.apply_presence(det, object()) == det and not j.fallback


def test_model_detection_is_dropped_when_the_tray_looks_empty():
    j = _judge(0.005)          # 빈 트레이 기준 사진과 같다
    det = [("can", 0.99, 10, 10, 20, 20)]      # 초록 부품을 캔으로 읽은 경우
    assert j.apply_presence(det, object()) == [] and not j.fallback


def test_off_when_no_presence_function():
    j = _judge(0.9)
    j.presence = None
    assert j.apply_presence([], object()) == []


def test_paper_decision_after_three_frames():
    j = _judge(0.2)
    out = [j.detector.update(j.apply_presence([], object()), i * 100)[0] for i in range(3)]
    assert out == ["none", "none", "decision"]
