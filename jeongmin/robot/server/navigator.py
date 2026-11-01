"""통(정류장) 찾아가기 + 쏟기 + 출발점으로 돌아오기.

움직이는 방식: '조금 움직이고 → 멈춰서 보고 → 다시 판단'. 화면이 흔들리지 않고, 중간에 끊겨도 로봇이 선다.

  decide()  : 지금 보이는 마커·초음파 거리 → 다음 한 걸음 (하드웨어와 상관없는 순수 함수, 테스트하기 쉬움)
  Mission   : decide() 를 반복해서 실제로 움직이는 백그라운드 작업

한 걸음 판단
  목표 마커가 안 보이면 (움직임을 줄이려고 정해진 만큼만 찾는다)
    look   : 몸은 두고 카메라만 좌우로 돌려 본다 → 목표가 보이면 그쪽으로 한 번 회전
    scan   : 그래도 없으면 몸을 딱 한 바퀴 돌며 보이는 블록(번호를 못 읽은 것 포함)의 방향을 기록
    visit  : 기록한 미확인 블록으로 하나씩 돌아서 다가가 번호 확인
             → 목표면 그대로 찾아가기, 아니면 다가간 만큼 물러나 다음 블록. 다 보면 실패
  방향은 회전 시간으로 어림한다 (turn90_ms, turn_dead_ms). 카메라 시야 반폭 half_fov_deg.
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

from .vision import CANDIDATE, Marker


@dataclass
class NavConfig:
    speed: int = 70           # 다가갈 때 속도
    turn_speed: int = 60      # 회전 속도
    pulse_ms: int = 250       # 한 걸음 움직이는 시간
    settle_ms: int = 150      # 멈추고 화면이 안정될 때까지
    center_tol: float = 0.15  # |cx| 가 이 안이면 가운데
    arrive_size: float = 0.3  # 마커가 화면 너비의 이만큼이면 도착
    arrive_cm: float = 25     # 가운데를 보고 있고 초음파가 이보다 가까우면 도착
    search_steps: int = 40    # (예전 방식) 회전하며 찾는 최대 걸음
    turn_dead_ms: int = 120   # 회전 명령 중 출발하느라 거의 안 도는 시간 (실측: 0.2초에 약 15°)
    scan_step_ms: int = 350   # 한 바퀴 둘러볼 때 한 번에 도는 시간
    half_fov_deg: float = 30  # 카메라 시야의 반 (cx ±1 이 ±이만큼의 각도)
    visit_steps: int = 14     # 미확인 블록 하나에 다가가며 확인하는 최대 걸음
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


def turn_ms_for(cx: float, cfg: NavConfig) -> int:
    """마커가 화면 cx 에 있을 때 가운데로 오게 도는 시간 = 출발 시간 + 각도만큼 (짧게 돌리면 출발하느라 안 돈다)"""
    deg = abs(cx) * cfg.half_fov_deg
    return int(cfg.turn_dead_ms + deg * max(1, cfg.turn90_ms - cfg.turn_dead_ms) / 90)


def decide(markers: list[Marker], target: int, cm: float, cfg: NavConfig, last_cx: float = 0.0) -> Step:
    m = next((m for m in markers if m.id == target), None)
    if m is None:
        far = [x for x in markers if x.id == CANDIDATE]
        if not far:
            return Step("search", "turn_right" if last_cx > 0 else "turn_left", cfg.turn_speed, cfg.pulse_ms)
        cx = sum(x.cx for x in far) / len(far)  # 어느 게 목표인지 모르니 무리의 가운데로
        if abs(cx) > cfg.center_tol:
            return Step("closer", "turn_right" if cx > 0 else "turn_left", cfg.turn_speed, turn_ms_for(cx, cfg))
        return Step("closer", "forward", cfg.speed, cfg.pulse_ms)
    centered = abs(m.cx) <= cfg.center_tol
    if m.size >= cfg.arrive_size or (centered and 0 < cm <= cfg.arrive_cm):
        return Step("arrived")
    if not centered:
        return Step("align", "turn_right" if m.cx > 0 else "turn_left", cfg.turn_speed, turn_ms_for(m.cx, cfg))
    return Step("approach", "forward", cfg.speed, cfg.pulse_ms)


class NavError(Exception):
    pass


class Mission:
    """한 번에 하나만. robot 은 main.Robot (move, blocked, driver, vision)."""

    def __init__(self, robot, stations: dict, cfg: NavConfig, sleep=asyncio.sleep) -> None:
        self.robot, self.stations, self.cfg, self.sleep = robot, stations, cfg, sleep
        self.state = {"phase": "idle", "station": None, "target": None, "message": "", "steps": 0}
        self.seen: list[Marker] = []
        self.heading = 0.0  # 임무 시작 방향 기준 대략의 방향(도), + = 왼쪽
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
        if self.robot.blocked:
            raise NavError("앞에 장애물이 있어 멈췄습니다")
        await self.sleep(ms / 1000)
        await self._stop()
        await self.sleep(self.cfg.settle_ms / 1000)
        self.heading += self._turn_deg(action, ms)

    def _turn_deg(self, action: str, ms: int) -> float:
        """회전 시간 → 대략의 각도 (+ = 왼쪽)"""
        if action not in ("turn_left", "turn_right"):
            return 0.0
        cfg = self.cfg
        deg = max(0, ms - cfg.turn_dead_ms) * 90 / max(1, cfg.turn90_ms - cfg.turn_dead_ms)
        return deg if action == "turn_left" else -deg

    async def _turn_to(self, heading: float) -> None:
        """기록해 둔 방향(도)으로 시간 회전"""
        cfg = self.cfg
        diff = (heading - self.heading + 180) % 360 - 180
        if abs(diff) < cfg.half_fov_deg * cfg.center_tol:
            return
        ms = int(abs(diff) * max(1, cfg.turn90_ms - cfg.turn_dead_ms) / 90 + cfg.turn_dead_ms)
        await self._pulse("turn_left" if diff > 0 else "turn_right", cfg.turn_speed, ms)

    def _bearing(self, m: Marker) -> float:
        return self.heading - m.cx * self.cfg.half_fov_deg  # cx + = 화면 오른쪽 = 방향 −

    async def _scan(self, info: dict) -> list[dict]:
        """몸을 한 바퀴 돌며 보이는 블록을 기록. 목표가 보이면 그 자리에서 멈춘다 (목표를 보고 있음)."""
        cfg, target = self.cfg, info["marker"]
        self._set("scan", f"{info['label']} (마커 {target}) 한 바퀴 둘러보는 중")
        start, sightings = self.heading, []
        while True:
            self.seen = await asyncio.to_thread(self.robot.vision.markers)
            for m in self.seen:
                sightings.append({"id": m.id, "bearing": self._bearing(m), "size": m.size})
            if any(m.id == target for m in self.seen) or abs(self.heading - start) >= 360:
                return sightings
            before = self.heading
            await self._pulse("turn_left", cfg.turn_speed, cfg.scan_step_ms)
            if self.heading == before:  # 각도 설정이 이상하면 끝없이 돌지 않게
                return sightings

    def _unknowns(self, sightings: list[dict], target: int, done: list[float]) -> list[float]:
        """기록에서 아직 확인 안 한 블록 방향들 (가까운(큰) 것부터). 번호를 읽은 다른 통은 빼고, 비슷한 방향은 하나로."""
        tol = self.cfg.half_fov_deg / 2

        def near(a: float, b: float) -> bool:
            return abs((a - b + 180) % 360 - 180) < tol

        others = [x["bearing"] for x in sightings if x["id"] not in (target, CANDIDATE)]
        picks: list[dict] = []
        for x in sorted(sightings, key=lambda x: -x["size"]):
            if x["id"] != CANDIDATE or any(near(x["bearing"], o) for o in others + done):
                continue
            if not any(near(x["bearing"], p["bearing"]) for p in picks):
                picks.append(x)
        return [p["bearing"] for p in picks]

    async def _visit(self, info: dict, bearing: float) -> bool:
        """기록한 방향의 미확인 블록에 다가가 번호 확인. 목표면 True (목표를 보는 채로), 아니면 물러나고 False."""
        cfg, target = self.cfg, info["marker"]
        self._set("visit", f"{info['label']} (마커 {target}) 인지 블록 확인하러 가는 중")
        await self._turn_to(bearing)
        forward = 0
        try:
            for _ in range(cfg.visit_steps):
                self.seen = await asyncio.to_thread(self.robot.vision.markers)
                if any(m.id == target for m in self.seen):
                    return True
                ahead = [m for m in self.seen if abs(m.cx) < 0.5]
                if not ahead or any(m.id != CANDIDATE for m in ahead if abs(m.cx) < 0.25):
                    return False  # 앞에 블록이 없거나, 가운데 블록 번호를 읽었는데 목표가 아님
                c = min(ahead, key=lambda m: abs(m.cx))
                if abs(c.cx) > cfg.center_tol:
                    await self._pulse("turn_right" if c.cx > 0 else "turn_left", cfg.turn_speed, turn_ms_for(c.cx, cfg))
                else:
                    await self._pulse("forward", cfg.speed, cfg.pulse_ms)
                    forward += 1
            return False
        finally:
            if forward and not any(m.id == target for m in self.seen):
                await self._pulse("backward", cfg.speed, forward * cfg.pulse_ms)  # 처음 자리로


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
            await self._pulse("turn_right" if m.cx > 0 else "turn_left", cfg.turn_speed, turn_ms_for(m.cx, cfg))
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
        target = info["marker"]
        self.state["target"] = name
        last_size, looked, sightings, done = 0.0, False, None, []
        for _ in range(cfg.step_limit):
            self.seen = await asyncio.to_thread(self.robot.vision.markers)
            self.state["steps"] += 1
            m = next((m for m in self.seen if m.id == target), None)
            if m is None:
                if last_size >= cfg.arrive_size * cfg.lost_near:
                    # 바로 전 걸음에 크게 보였는데 사라짐 = 너무 가까워 화면 밖 (카메라가 정면 고정이라 낮은 마커는 아래로 빠진다)
                    self._set("arrived", f"{info['label']} (마커 {target}) 가까워서 안 보임 → 도착")
                    await self._stop()
                    return
                last_size = 0.0
                if not looked:  # 1) 카메라만 둘러보기 → 보이면 그쪽으로 한 번 회전
                    looked = True
                    side = await self._look_around(info)
                    if side is not None:
                        await self._pulse("turn_right" if side > 0 else "turn_left", cfg.turn_speed, cfg.turn90_ms // 2)
                    continue
                if sightings is None:  # 2) 몸으로 한 바퀴만
                    sightings = await self._scan(info)
                    continue
                todo = self._unknowns(sightings, target, done)  # 3) 미확인 블록 하나씩
                if not todo:
                    raise NavError(f"{info['label']} 마커 {target} 번을 못 찾았습니다 (한 바퀴 둘러보고 블록 {len(done)}개 확인)")
                done.append(todo[0])
                await self._visit(info, todo[0])
                continue
            cm = await asyncio.to_thread(self.robot.driver.distance_cm)
            step = decide(self.seen, target, cm, cfg)
            self._set(step.phase, f"{info['label']} (마커 {target})")
            if step.phase == "arrived":
                await self._stop()
                return
            last_size = m.size
            await self._pulse(step.action, step.speed, step.ms)
        raise NavError(f"{info['label']} 까지 너무 오래 걸립니다 (걸음 {cfg.step_limit} 초과)")
