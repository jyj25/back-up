"""통(정류장) 찾아가기 + 쏟기 + 출발점으로 돌아오기.

움직이는 방식: '조금 움직이고 → 멈춰서 보고 → 다시 판단'. 화면이 흔들리지 않고, 중간에 끊겨도 로봇이 선다.

  decide()  : 지금 보이는 마커·초음파 거리 → 다음 한 걸음 (하드웨어와 상관없는 순수 함수, 테스트하기 쉬움)
  Mission   : decide() 를 반복해서 실제로 움직이는 백그라운드 작업

한 걸음 판단
  목표 마커가 안 보임        → search   : 마지막으로 본 쪽으로 제자리 회전
  가운데에서 벗어남          → align    : 그쪽으로 조금 회전 (많이 벗어날수록 길게)
  가운데 + 아직 멂           → approach : 앞으로 조금
  마커가 충분히 큼 / 초음파 가까움 → arrived
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, fields

from .vision import Marker


@dataclass
class NavConfig:
    speed: int = 70           # 다가갈 때 속도
    turn_speed: int = 60      # 회전 속도
    pulse_ms: int = 250       # 한 걸음 움직이는 시간
    settle_ms: int = 150      # 멈추고 화면이 안정될 때까지
    center_tol: float = 0.15  # |cx| 가 이 안이면 가운데
    arrive_size: float = 0.3  # 마커가 화면 너비의 이만큼이면 도착
    arrive_cm: float = 25     # 가운데를 보고 있고 초음파가 이보다 가까우면 도착
    search_steps: int = 40    # 이만큼 돌아도 못 찾으면 실패 (250ms × 40 ≈ 한 바퀴 반)
    step_limit: int = 300     # 한 정류장까지 최대 걸음 수
    backup_ms: int = 600      # 쏟은 뒤 뒤로 빠지는 시간

    @classmethod
    def from_dict(cls, d: dict) -> "NavConfig":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Step:
    phase: str                # search | align | approach | arrived
    action: str | None = None
    speed: int = 0
    ms: int = 0


def decide(markers: list[Marker], target: int, cm: float, cfg: NavConfig, last_cx: float = 0.0) -> Step:
    m = next((m for m in markers if m.id == target), None)
    if m is None:
        return Step("search", "turn_right" if last_cx > 0 else "turn_left", cfg.turn_speed, cfg.pulse_ms)
    centered = abs(m.cx) <= cfg.center_tol
    if m.size >= cfg.arrive_size or (centered and 0 < cm <= cfg.arrive_cm):
        return Step("arrived")
    if not centered:
        ms = max(60, int(cfg.pulse_ms * min(1.0, abs(m.cx))))
        return Step("align", "turn_right" if m.cx > 0 else "turn_left", cfg.turn_speed, ms)
    return Step("approach", "forward", cfg.speed, cfg.pulse_ms)


class NavError(Exception):
    pass


class Mission:
    """한 번에 하나만. robot 은 main.Robot (move, blocked, driver, vision)."""

    def __init__(self, robot, stations: dict, cfg: NavConfig, sleep=asyncio.sleep) -> None:
        self.robot, self.stations, self.cfg, self.sleep = robot, stations, cfg, sleep
        self.state = {"phase": "idle", "station": None, "target": None, "message": "", "steps": 0}
        self.seen: list[Marker] = []
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, station: str, dump: bool = True, return_home: bool = True) -> None:
        if self.running:
            raise RuntimeError("이미 임무 중입니다")
        self.state = {"phase": "starting", "station": station, "target": station, "message": "", "steps": 0}
        self._task = asyncio.create_task(self._run(station, dump, return_home))

    def cancel(self, reason: str = "취소") -> bool:
        if not self.running:
            return False
        self._task.cancel()
        self._set("cancelled", reason)
        return True

    async def abort(self, reason: str = "취소") -> bool:
        """취소하고 정리(정지)가 끝날 때까지 기다린다. 이벤트 루프 안에서 부를 것."""
        if not self.cancel(reason):
            return False
        await self.wait()
        return True

    async def wait(self) -> None:
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _set(self, phase: str, message: str = "") -> None:
        self.state["phase"], self.state["message"] = phase, message

    async def _stop(self) -> None:
        await asyncio.to_thread(self.robot.driver.stop)

    async def _run(self, station: str, dump: bool, return_home: bool) -> None:
        try:
            await asyncio.to_thread(self.robot.driver.set_servo, 90, None)  # 카메라 정면
            await self._go(station)
            if dump:
                self._set("dumping", f"{self.stations[station]['label']} 에 쏟는 중")
                await asyncio.to_thread(self.robot.driver.dump)
                self._set("backing")
                self.robot.move("backward", self.cfg.speed, self.cfg.backup_ms)
                await self.sleep(self.cfg.backup_ms / 1000)
                await self._stop()
            if return_home and station != "home":
                await self._go("home")
            self._set("done", "완료")
        except NavError as e:
            await self._stop()
            self._set("failed", str(e))
        except asyncio.CancelledError:
            await self._stop()
            raise

    async def _go(self, name: str) -> None:
        cfg, info = self.cfg, self.stations[name]
        self.state["target"] = name
        last_cx, searched = 0.0, 0
        for _ in range(cfg.step_limit):
            self.seen = await asyncio.to_thread(self.robot.vision.markers)
            cm = await asyncio.to_thread(self.robot.driver.distance_cm)
            step = decide(self.seen, info["marker"], cm, cfg, last_cx)
            self.state["steps"] += 1
            self._set(step.phase, f"{info['label']} (마커 {info['marker']})")
            if step.phase == "arrived":
                await self._stop()
                return
            if step.phase == "search":
                searched += 1
                if searched > cfg.search_steps:
                    raise NavError(f"{info['label']} 마커 {info['marker']} 번을 못 찾았습니다")
            else:
                searched = 0
                last_cx = next(m.cx for m in self.seen if m.id == info["marker"])
            # 서버 자동 정지는 여유 있게, 실제 정지는 여기서 직접
            self.robot.move(step.action, step.speed, step.ms + 300)
            if self.robot.blocked:
                raise NavError("앞에 장애물이 있어 멈췄습니다")
            await self.sleep(step.ms / 1000)
            await self._stop()
            await self.sleep(cfg.settle_ms / 1000)
        raise NavError(f"{info['label']} 까지 너무 오래 걸립니다 (걸음 {cfg.step_limit} 초과)")
