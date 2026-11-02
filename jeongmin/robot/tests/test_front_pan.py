"""카메라 정면 각도: 코드의 pan 90 이 실제 서보의 CAMERA_FRONT_PAN 이 된다."""
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import drivers  # noqa: E402


def test_default_front_pan_is_unchanged():
    assert drivers.PAN_FRONT == 90 or os.environ.get("CAMERA_FRONT_PAN")      # 설정이 없으면 예전과 같다
    assert drivers.physical_pan(0) >= 0 and drivers.physical_pan(180) <= 180


def test_physical_pan_follows_the_front_setting_and_clamps(monkeypatch):
    monkeypatch.setattr(drivers, "PAN_FRONT", 135)         # 90°에서 오른쪽, 180°에서 왼쪽을 본다 → 정면은 그 중간
    assert drivers.physical_pan(90) == 135                  # 코드의 '정면'이 실제 135°
    assert drivers.physical_pan(0) == 45                    # 오른쪽 끝
    assert drivers.physical_pan(180) == 180                 # 왼쪽은 서보 끝에서 자른다
    assert drivers.physical_pan(130) == 175
    monkeypatch.setattr(drivers, "PAN_FRONT", 90)
    assert [drivers.physical_pan(p) for p in (0, 90, 180)] == [0, 90, 180]
