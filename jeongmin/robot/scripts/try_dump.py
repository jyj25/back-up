"""쏟기만 시험 (라즈베리파이에서): 통에 도착했다고 치고 옆면 대기 → 쏟기 → 빠지기 → 되돌아 회전.

    ~/raspbot-venv/bin/python scripts/try_dump.py           stations.json 의 can
    STATIONS_FILE=stations.blocks.json ~/raspbot-venv/bin/python scripts/try_dump.py can
    ~/raspbot-venv/bin/python scripts/try_dump.py --no-turn    회전·옆걸음 없이 쏟기만 (트레이 시연)

조종 서버가 켜져 있으면 먼저 끈다 (하드웨어를 같이 쓰면 안 됨). 리모컨 전원 버튼을 누르면 멈춘다.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

ROBOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT))
os.chdir(ROBOT)
os.environ.setdefault("BOARD_PORT", "none")
os.environ.setdefault("HISTORY_FILE", "none")

from server import main  # noqa: E402


async def run(robot, station: str, turn: bool = True) -> None:
    m = robot.mission
    await robot.start()  # 리모컨 비상 정지·자동 정지 감시
    print("1초 뒤 시작", flush=True)
    await asyncio.sleep(1)
    t = time.time()
    if not turn:
        await asyncio.to_thread(robot.driver.dump)
        print(f"끝 ({time.time() - t:.1f}초)")
        return
    strafed = await m._dock_side(m.stations[station]) if m.cfg.dump_side else 0
    print(f"옆면 대기: 옆걸음 {strafed}번, 보이는 마커 {[(x.id, round(x.cx, 2), round(x.size, 3)) for x in m.seen]}", flush=True)
    await asyncio.to_thread(robot.driver.dump)
    if m.cfg.dump_side:
        if strafed:
            away = "strafe_left" if m.cfg.dump_side == "right" else "strafe_right"
            await m._pulse(away, m.cfg.speed, strafed * m.cfg.pulse_ms)
        back = "turn_right" if m.cfg.dump_side == "right" else "turn_left"
        await m._pulse(back, m.cfg.turn_speed, m.cfg.turn90_ms)
    await asyncio.to_thread(robot.driver.set_servo, 90, None)
    print(f"끝 ({time.time() - t:.1f}초)")


def cli() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    turn = "--no-turn" not in sys.argv
    station = args[0] if args else "can"
    robot = main.Robot()

    async def guarded():
        try:
            await asyncio.wait_for(run(robot, station, turn), 60)
        finally:
            robot.driver.stop()

    try:
        asyncio.run(guarded())
    finally:
        robot.close()


if __name__ == "__main__":
    cli()
