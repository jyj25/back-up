"""다수결 확정: 캔과 페트처럼 비슷하게 의심되는 물건."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server.judge import Detector  # noqa: E402


def box(label, conf, x=10, y=10):
    return (label, conf, x, y, 8, 8)


def run(det, frames):
    return [det.update(f, i * 33) for i, f in enumerate(frames)]


def pattern(pet_share, n, pet=0.95, can=0.93):
    """프레임마다 1등이 페트 또는 캔 (사진의 페트병: 20장 중 16장이 페트 1등)"""
    out, acc = [], 0.0
    for _ in range(n):
        acc += pet_share
        if acc >= 1.0:
            acc -= 1.0
            out.append([box("pet", pet), box("can", can - 0.05, 60, 60)])
        else:
            out.append([box("can", can), box("pet", pet - 0.05, 60, 60)])
    return out


def test_mostly_pet_bottle_is_decided_as_pet_not_can():
    r = run(Detector(vote_n=12), pattern(0.8, 40))
    decisions = [x for x in r if x[0] == "decision"]
    assert decisions and decisions[0][1] == "pet", [x[:2] for x in r if x[0] == "decision"]


def test_truly_ambiguous_object_is_not_decided():
    r = run(Detector(vote_n=12), pattern(0.5, 120))
    assert all(x[0] == "none" for x in r)


def test_not_decided_before_the_window_is_full():
    r = run(Detector(vote_n=12), [[box("pet", 0.95)]] * 11)
    assert all(x[0] == "none" for x in r)
    assert run(Detector(vote_n=12), [[box("pet", 0.95)]] * 12)[-1][0] == "decision"


def test_empty_or_weak_frames_count_against_a_decision():
    frames = ([[box("can", 0.95)]] * 5 + [[]] * 7) * 3                 # 절반 가까이 물체가 안 보임
    assert all(x[0] == "none" for x in run(Detector(vote_n=12), frames))


def test_progress_streak_grows_toward_the_decision():
    d = Detector(vote_n=12)
    seen = [d.update([box("can", 0.95)], i)[0] for i in range(6)]
    assert d.streak >= 1 and "decision" not in seen


def test_waits_for_empty_tray_after_a_decision_then_decides_again():
    d = Detector(vote_n=6)
    assert run(d, [[box("can", 0.95)]] * 6)[-1][0] == "decision"
    assert all(x[0] != "decision" for x in run(d, [[box("can", 0.95)]] * 20))   # 물건이 그대로 → 새 판정 없음
    run(d, [[]] * 3)                                                           # 빈 트레이 3번 → 다시 판정 가능
    assert run(d, [[box("pet", 0.95)]] * 6)[-1][:2] == ("decision", "pet")


def test_default_detector_keeps_the_consecutive_rule():
    r = run(Detector(), [[box("can", 0.95)]] * 3)                           # vote_n 기본 0 → 예전 방식
    assert r[2][0] == "decision"
