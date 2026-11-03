"""쏟은 뒤 출발선으로 돌아온다 (전진한 시간만큼 후진)."""
import asyncio
import os

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from server import main  # noqa: E402


def test_returns_to_start_after_dump():
    nav = main.Robot().mission  # 새 로봇이라 다른 시험에 영향이 없다
    moves = []

    async def pulse(action, speed, ms):
        moves.append((action, ms))
        nav._net_ms += {"forward": ms, "backward": -ms}[action]

    old_pulse, old_net = nav._pulse, nav._net_ms
    nav._pulse = pulse
    nav._net_ms = 1000 + 150
    try:
        asyncio.run(nav._return_to_start())
    finally:
        nav._pulse = old_pulse
    assert sum(ms for a, ms in moves if a == "backward") == 1150 and all(a == "backward" for a, _ in moves)
    assert abs(nav._net_ms) < 50
    nav._net_ms = old_net
