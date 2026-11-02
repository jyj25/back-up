"""출발(READY)은 확정을 기다리지 않고 지금 프레임에서 퍼센트가 제일 높은 종류로 간다."""
import asyncio
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402
from server.judge import Detector, PiJudge  # noqa: E402


def test_frame_obj_has_top_class():
    j = PiJudge.__new__(PiJudge)
    j.detector = Detector()
    o = PiJudge.frame_obj(j, [("can", 0.7, 0, 0, 8, 8), ("pet", 0.93, 20, 0, 8, 8)], 2, 40)
    assert o["top"] == {"class": "pet", "conf": 0.93}
    assert PiJudge.frame_obj(j, [], 0, 40)["top"] is None


def test_go_now_uses_highest_percent_without_decision():
    async def go():
        robot = main.Robot()
        sorter = robot.sorter
        sorter.handle({"event": "frame", "class": None, "conf": 0.0, "ms": 40, "n": 2,
                       "top": {"class": "pet", "conf": 0.91}})
        started = []
        sorter.start = lambda label, **kw: started.append(label)
        r = sorter.go_now()
        robot.close()
        return r, started

    r, started = asyncio.run(go())
    assert r["ok"] and started == ["pet"]
