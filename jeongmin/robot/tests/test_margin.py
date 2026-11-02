"""헷갈리는 장면(다른 종류와 확신도 격차가 작음)은 확정하지 않는다."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server.judge import Detector, PiJudge  # noqa: E402


def box(label, conf, x=10, y=10):
    return (label, conf, x, y, 8, 8)


def run(det, frames):
    return [det.update(f, i * 100) for i, f in enumerate(frames)]


def test_ambiguous_can_vs_pet_is_not_decided():
    frame = [box("pet", 0.90, 10, 10), box("can", 0.85, 60, 60)]    # 격차 0.05
    assert all(r[0] == "none" for r in run(Detector(margin=0.3), [frame] * 10))


def test_clear_winner_is_decided_even_with_a_weak_other():
    frame = [box("pet", 0.95, 10, 10), box("can", 0.62, 60, 60)]    # 격차 0.33
    r = run(Detector(margin=0.3), [frame] * 3)
    assert r[2][0] == "decision" and r[2][1] == "pet"


def test_margin_zero_keeps_old_behavior():
    frame = [box("pet", 0.90, 10, 10), box("can", 0.85, 60, 60)]
    r = run(Detector(margin=0), [frame] * 3)
    assert r[2][0] == "decision" and r[2][1] == "pet"


def test_margin_only_looks_at_other_classes_not_same_class_cells():
    frame = [box("can", 0.95, 10, 10), box("can", 0.90, 60, 60)]    # 같은 종류가 두 곳 → 격차 조건과 무관
    r = run(Detector(), [frame] * 3)
    assert r[2][0] == "decision" and r[2][1] == "can"


def test_decision_snapshot_is_saved_and_trimmed(tmp_path):
    import server.judge as judge
    j = PiJudge(cam=None, model_path="/none/model/x.eim", on_line=lambda line: None)
    j.log_dir = tmp_path
    old_keep, judge.LOG_KEEP = judge.LOG_KEEP, 2
    try:
        for i in range(4):
            j._save_decision(b"\xff\xd8jpg", "can", 0.9 + i / 100, [("can", 0.9, 1, 2, 8, 8)])
            os.utime(next(iter(sorted(tmp_path.glob("*.jpg")))), None)
    finally:
        judge.LOG_KEEP = old_keep
    assert len(list(tmp_path.glob("*.jpg"))) <= 4                      # 같은 초에 만든 파일은 이름이 겹쳐 덮어쓸 수 있다
    assert (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").count("\n") == 4
