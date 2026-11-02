"""파이 판정의 확정 로직 시험 (detect_logic.h 와 같은 규칙)."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server.judge import Detector  # noqa: E402


def box(label, conf=0.95, x=10, y=10):
    return (label, conf, x, y, 8, 8)


def run(det, frames):
    out = []
    for i, f in enumerate(frames):
        out.append(det.update(f, i * 100))
    return out


def test_decision_after_three_same_frames():
    r = run(Detector(), [[box("can")]] * 3)
    assert [x[0] for x in r] == ["none", "none", "decision"]
    assert r[2][1] == "can" and r[2][2] >= 0.8


def test_no_decision_when_label_changes():
    r = run(Detector(), [[box("can")], [box("pet")], [box("can")]])
    assert all(x[0] == "none" for x in r)


def test_no_decision_under_confidence():
    r = run(Detector(), [[box("paper", 0.7)]] * 5)
    assert all(x[0] == "none" for x in r)


def test_adjacent_cells_form_one_object_and_far_cells_do_not():
    d = Detector()
    near = [box("can", 0.9, 10, 10), box("can", 0.95, 18, 10)]   # 붙어 있음 → 물체 1개
    assert d.update(near, 0)[3] == 1
    far = [box("can", 0.9, 10, 10), box("can", 0.95, 60, 60)]    # 떨어져 있음 → 물체 2개
    assert Detector().update(far, 0)[3] == 2


def test_picks_highest_confidence_object():
    frame = [box("pet", 0.65, 10, 10), box("can", 0.97, 70, 70)]
    r = run(Detector(), [frame] * 3)
    assert r[2][0] == "decision" and r[2][1] == "can"


def test_waits_for_empty_tray_before_next_decision():
    d = Detector()
    run(d, [[box("can")]] * 3)                       # 확정
    r = run(d, [[box("can")]] * 5)                   # 물건이 그대로 → 새 판정 없음
    assert all(x[0] != "decision" for x in r)
    run(d, [[]] * 3)                                 # 3번 연속 빈 트레이 → 다시 판정 가능
    r = run(d, [[box("pet")]] * 3)
    assert r[2][0] == "decision" and r[2][1] == "pet"


def test_stuck_event_when_not_cleared():
    d = Detector(stuck_ms=1000)
    run(d, [[box("can")]] * 3)
    assert d.update([box("can")], 5000)[0] == "stuck"
