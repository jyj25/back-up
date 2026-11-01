"""통(정류장) 찾아가기 + 쏟기 + 출발점으로 돌아오기.

움직이는 방식: '조금 움직이고 → 멈춰서 보고 → 다시 판단'. 화면이 흔들리지 않고, 중간에 끊겨도 로봇이 선다.

  decide()  : 지금 보이는 마커·초음파 거리 → 다음 한 걸음 (하드웨어와 상관없는 순수 함수, 테스트하기 쉬움)
  Mission   : decide() 를 반복해서 실제로 움직이는 백그라운드 작업

한 걸음 판단
  목표 마커가 안 보임        → look     : 몸은 두고 카메라만 좌우로 돌려 찾아본다 (찾으면 그쪽으로 회전)
                               search   : 그래도 없으면 마지막으로 본 쪽으로 제자리 회전 (가끔 다시 둘러봄)
  가운데에서 벗어남          → align    : 그쪽으로 조금 회전 (많이 벗어날수록 길게)
  가운데 + 아직 멂           → approach : 앞으로 조금
  마커가 충분히 큼 / 초음파 가까움 → arrived

쏟기 (dump_side 가 있으면): 트레이가 옆으로 쏟으므로 쏟는 쪽 옆면을 통에 댄다
  카메라를 그쪽 옆(90°)으로 → 시간으로 약 90° 회전 → 옆 화면에 마커가 보이면 가운데로 보정 + 커질 때까지 옆걸음
  (안 보이면 그 자리에서) → 쏟기 → 옆걸음한 만큼 빠지기 → 원래 방향으로 되돌아 회전 → 카메라 정면
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, fields

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
    lost_near: float = 0.6    # 마커가 arrive_size 의 이만큼 이상 컸다가 사라지면 도착 (가까워져 화면 아래로 빠짐)
    dump_side: str | None = None  # 트레이가 쏟는 쪽 "left" / "right" (None 이면 정면으로 멈춘 채 쏟음)
    dock_size: float = 0.35   # 옆걸음으로 다가갈 때 마커가 이만큼 크면 멈춤
    dock_steps: int = 12      # 옆면 보정·옆걸음 최대 걸음
    turn90_ms: int = 500      # turn_speed 로 약 90° 도는 시간 (실측: 60 으로 1초에 약 180°, 바닥에 따라 다름)
    look_angles: list[int] = field(default_factory=lambda: [50, 130, 20, 160])  # 둘러볼 카메라 각도 (90 정면, 클수록 왼쪽)
    look_every: int = 12      # 회전하며 찾는 중 이만큼마다 다시 둘러본다
    look_settle_ms: int = 400 # 카메라를 돌린 뒤 화면이 안정될 때까지
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
                side = self.cfg.dump_side
                strafed = await self._dock_side(self.stations[station]) if side else 0
                self._set("dumping", f"{self.stations[station]['label']} 에 쏟는 중")
                await asyncio.to_thread(self.robot.driver.dump)
                self._set("backing")
                if side:  # 옆걸음한 만큼 빠지고 원래 방향으로
                    if strafed:
                        away = "strafe_left" if side == "right" else "strafe_right"
                        await self._pulse(away, self.cfg.speed, strafed * self.cfg.pulse_ms)
                    back = "turn_right" if side == "right" else "turn_left"
                    await self._pulse(back, self.cfg.turn_speed, self.cfg.turn90_ms)
                    await asyncio.to_thread(self.robot.driver.set_servo, 90, None)
                else:
                    await self._pulse("backward", self.cfg.speed, self.cfg.backup_ms)
            if return_home and station != "home":
                await self._go("home")
            self._set("done", "완료")
        except NavError as e:
            await self._stop()
            self._set("failed", str(e))
        except asyncio.CancelledError:
            await self._stop()
            raise

    async def _pulse(self, action: str, speed: int, ms: int) -> None:
        self.robot.move(action, speed, ms + 300)  # 서버 자동 정지는 여유 있게, 실제 정지는 여기서
        await self.sleep(ms / 1000)
        await self._stop()
        await self.sleep(self.cfg.settle_ms / 1000)

    async def _dock_side(self, info: dict) -> int:
        """쏟는 쪽 옆면을 통에 댄다. 옆걸음한 걸음 수를 돌려준다 (빠질 때 씀). 마커를 못 봐도 실패하지 않고 그 자리에서 쏟는다."""
        cfg, target = self.cfg, info["marker"]
        side = cfg.dump_side
        self._set("docking", f"{info['label']} 쪽으로 옆면 맞추는 중")
        await asyncio.to_thread(self.robot.driver.set_servo, 0 if side == "right" else 180, None)  # 각도가 크면 왼쪽
        # 1) 시간으로 약 90° (오른쪽 면을 대려면 왼쪽으로 돈다)
        await self._pulse("turn_left" if side == "right" else "turn_right", cfg.turn_speed, cfg.turn90_ms)
        await self.sleep(cfg.look_settle_ms / 1000)
        # 2) 옆 화면에 마커가 보이면 가운데로 보정. 몸과 카메라가 같이 돌므로 판단은 정면과 같다
        m = None
        for _ in range(cfg.dock_steps):
            self.seen = await asyncio.to_thread(self.robot.vision.markers)
            m = next((m for m in self.seen if m.id == target), None)
            if m is None or abs(m.cx) <= cfg.center_tol:
                break
            ms = max(60, int(cfg.pulse_ms * min(1.0, abs(m.cx))))
            await self._pulse("turn_right" if m.cx > 0 else "turn_left", cfg.turn_speed, ms)
        # 3) 마커가 커질 때까지 통 쪽으로 옆걸음 (안 보이거나 가까이서 사라지면 멈춤)
        toward = "strafe_right" if side == "right" else "strafe_left"
        steps = 0
        while m is not None and m.size < cfg.dock_size and steps < cfg.dock_steps:
            await self._pulse(toward, cfg.speed, cfg.pulse_ms)
            steps += 1
            self.seen = await asyncio.to_thread(self.robot.vision.markers)
            m = next((m for m in self.seen if m.id == target), None)
        return steps

    async def _look_around(self, info: dict) -> float | None:
        """몸은 두고 카메라만 돌려 목표 마커를 찾는다 → 오른쪽이면 +1, 왼쪽이면 -1, 없으면 None"""
        self._set("look", f"{info['label']} (마커 {info['marker']}) 둘러보는 중")
        found = None
        try:
            for pan in self.cfg.look_angles:
                await asyncio.to_thread(self.robot.driver.set_servo, pan, None)
                await self.sleep(self.cfg.look_settle_ms / 1000)
                self.seen = await asyncio.to_thread(self.robot.vision.markers)
                if any(m.id == info["marker"] for m in self.seen):
                    found = -1.0 if pan > 90 else 1.0  # 각도가 크면 왼쪽을 보고 있다
                    break
        finally:
            await asyncio.to_thread(self.robot.driver.set_servo, 90, None)  # 다시 정면
            await self.sleep(self.cfg.look_settle_ms / 1000)
        return found

    async def _go(self, name: str) -> None:
        cfg, info = self.cfg, self.stations[name]
        self.state["target"] = name
        last_cx, last_size, searched = 0.0, 0.0, 0
        for _ in range(cfg.step_limit):
            self.seen = await asyncio.to_thread(self.robot.vision.markers)
            cm = await asyncio.to_thread(self.robot.driver.distance_cm)
            step = decide(self.seen, info["marker"], cm, cfg, last_cx)
            self.state["steps"] += 1
            self._set(step.phase, f"{info['label']} (마커 {info['marker']})")
            if step.phase == "arrived":
                await self._stop()
                return
            if step.phase == "search" and searched == 0 and last_size >= cfg.arrive_size * cfg.lost_near:
                # 바로 전 걸음에 크게 보였는데 사라짐 = 너무 가까워 화면 밖 (카메라가 정면 고정이라 낮은 마커는 아래로 빠진다)
                self._set("arrived", f"{info['label']} (마커 {info['marker']}) 가까워서 안 보임 → 도착")
                await self._stop()
                return
            if step.phase == "search":
                if searched % cfg.look_every == 0:
                    side = await self._look_around(info)
                    if side is not None:
                        last_cx = side
                        step = decide([], info["marker"], cm, cfg, last_cx)  # 찾은 쪽으로 회전
                searched += 1
                if searched > cfg.search_steps:
                    raise NavError(f"{info['label']} 마커 {info['marker']} 번을 못 찾았습니다")
            else:
                searched = 0
                m = next(m for m in self.seen if m.id == info["marker"])
                last_cx, last_size = m.cx, m.size
            # 서버 자동 정지는 여유 있게, 실제 정지는 여기서 직접
            self.robot.move(step.action, step.speed, step.ms + 300)
            if self.robot.blocked:
                raise NavError("앞에 장애물이 있어 멈췄습니다")
            await self.sleep(step.ms / 1000)
            await self._stop()
            await self.sleep(cfg.settle_ms / 1000)
        raise NavError(f"{info['label']} 까지 너무 오래 걸립니다 (걸음 {cfg.step_limit} 초과)")
