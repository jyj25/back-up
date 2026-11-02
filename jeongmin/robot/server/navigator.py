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
import time
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
    arrive_cx: float = 1.0    # 도착으로 치려면 마커가 이 가로 위치(|cx|) 안이어야 한다 (1.0 이면 위치는 안 봄). 작게 하면 마커를 가운데로 맞춘 뒤에 도착
    arrive_cm: float = 25     # 가운데를 보고 있고 초음파가 이보다 가까우면 도착
    search_steps: int = 40    # (예전 방식) 회전하며 찾는 최대 걸음
    turn_dead_ms: int = 120   # 회전 명령 중 출발하느라 거의 안 도는 시간 (실측: 0.2초에 약 15°)
    scan_step_ms: int = 350   # 한 바퀴 둘러볼 때 한 번에 도는 시간
    scan_pause_ms: int = 700  # 한 번 돈 뒤 멈춰서 화면이 안정되길 기다리는 시간 (그다음 마커를 찾는다)
    half_fov_deg: float = 30  # 카메라 시야의 반 (cx ±1 이 ±이만큼의 각도)
    visit_steps: int = 14     # 미확인 블록 하나에 다가가며 확인하는 최대 걸음
    look_frames: int = 3      # 한 번 볼 때 합쳐 볼 사진 수
    look_gap_ms: int = 80     # 그 사진 사이 간격
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
    finish_after_dump: bool = False  # True 면 쏟고 바로 끝 (뒤로 빠지거나 되돌아 돌지 않고, 출발점 복귀도 안 함)
    rescans: int = 0          # 번호가 맞는 블록을 못 찾으면 처음부터 다시 둘러보는 횟수 (그 블록은 반드시 있을 때)
    line_mode: bool = False   # True 면 마커를 일렬로 카메라가 볼 수 있게 세워 둔 경우: 몸으로 한 바퀴 돌며 찾지 않는다 (카메라 둘러보기까지만)
    line_advance_steps: int = 20  # 마커 일렬 모드에서 마커가 안 보일 때 앞으로 전진하며 찾는 최대 걸음 수 (한 걸음 = pulse_ms)
    side_camera: bool = False  # True 면 카메라가 로봇 오른쪽을 보고 마커 줄이 오른쪽에 있다: 화면의 좌우 = 몸의 앞뒤, 마커까지의 거리 = 오른쪽으로 얼마나 떨어졌나
    side_step_ms: int = 0     # 옆 카메라 모드에서 한 걸음 움직이는 시간 (0 이면 pulse_ms). 짧게 갈수록 마커를 놓치지 않고 한 번에 하나씩 확인한다
    side_hold: float = 0.0    # 옆 카메라로 줄을 따라 갈 때 마커 크기가 처음 본 크기에서 이 비율(0.35 = 35%) 넘게 달라지면 옆걸음으로 줄과의 간격을 되돌린다 (0 이면 끔). 길이 휘는 것을 막는다
    side_hold_max: int = 8    # 그렇게 간격을 되돌리는 최대 횟수
    pan_look: bool = False    # True 면: 로봇은 일직선으로 전진·후진만 한다 (옆걸음·회전 없음). 한 걸음마다 멈춰 카메라를 오른쪽(scan_pan)으로 돌려 마커를 확인하고, 아니면 카메라를 정면(travel_pan)으로 돌려 다음 걸음
    travel_pan: int = 135     # 달릴 때 카메라 각도 (정면)
    pan_step_ms: int = 250    # pan_look 에서 마커를 못 찾았을 때 한 걸음 전진하는 시간
    pan_back_margin: int = 6  # pan_look 에서 되돌아가며 찾을 때 출발점 뒤로 더 가 보는 걸음 수
    pan_judge_ms: int = 1500  # 마커가 처음 보이면 이만큼 멈춰서 '트레이와 같은 마커인가' 판단한다 (다른 번호면 그 뒤 전진). 같은 마커는 한 번만
    pan_center: bool = False  # False 면 목표 마커가 화면 어디든 보이는 순간 멈춰서 바로 쏟는다. True 면 줄 방향으로 가운데에 맞춘 뒤 쏟는다
    pan_align_ms: int = 150   # 목표 마커가 보일 때 가운데에 맞추려는 한 걸음 시간
    pan_align_max: int = 14   # 가운데에 맞추는 최대 걸음
    scan_pan: int = 90        # 임무를 시작할 때 카메라를 돌려 놓는 각도 (코드의 pan 값: 90 = CAMERA_FRONT_PAN 이 가리키는 곳, 지금은 로봇 오른쪽 마커 줄)
    scan_pause_ms: int = 0    # 카메라를 돌린 뒤 마커를 알아보도록 멈춰 있는 시간
    side_approach: bool = False  # 옆 카메라 모드에서 마커가 가운데 오면 바로 서서 쏟지 않고 오른쪽으로 더 다가갈지
    fail_retries: int = 0     # 마커를 못 찾는 등으로 실패하면 (줄 따라가기면 전진한 만큼 뒤로 물러난 뒤) 마커를 다시 찾으러 가는 횟수
    row_mode: bool = False    # True 면 줄 따라가기: 회전·카메라 둘러보기·한 바퀴 돌기 없이 전진·후진·옆 이동만으로 목표 마커 앞에 선다
    back_size: float = 0.0    # 줄 따라가기에서 마커가 이만큼보다 크게 보이면 너무 가까운 것 → 후진 (0 이면 arrive_size 의 1.8배)
    ahead_cx: float = 0.7     # 앞쪽 마커 후보로 칠 가로 위치 범위 (|cx| 가 이 안이면 앞에 있다고 보고 먼저 다가감)

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
    if (m.size >= cfg.arrive_size and abs(m.cx) <= cfg.arrive_cx) or (centered and 0 < cm <= cfg.arrive_cm):
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
        self._net = 0       # 앞으로 간 걸음 - 뒤로 간 걸음 (실패 뒤 제자리로 돌아오는 데 쓴다)
        self.moves: list = []  # 이번 임무에서 바퀴에 보낸 명령 (시각, 동작, ms) — 어떻게 움직였는지 나중에 확인한다
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, station: str, dump: bool = True, return_home: bool = True) -> None:
        if self.running:
            raise RuntimeError("이미 임무 중입니다")
        self.state = {"phase": "starting", "station": station, "target": station, "message": "", "steps": 0}
        self.moves = []
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
            if not self.cfg.pan_look:
                self._set("starting", "카메라를 마커 쪽으로 돌리는 중")
                await asyncio.to_thread(self.robot.driver.set_servo, self.cfg.scan_pan, None)  # 카메라를 마커 줄 쪽으로
            if self.cfg.scan_pause_ms and not self.cfg.pan_look:
                await self.sleep(self.cfg.scan_pause_ms / 1000)  # 돌아간 화면이 안정되고 마커를 알아볼 때까지 멈춰 있는다
            await self._go_with_retries(station)
            if dump:
                side = self.cfg.dump_side
                strafed = await self._dock_side(self.stations[station]) if side else 0
                await self._dump_with_tray(self.stations[station]['label'])
                if not self.cfg.finish_after_dump:
                    self._set("backing")
                if self.cfg.finish_after_dump:
                    pass  # 블록 앞에서 왼쪽으로 90° 돌아 쏟았으면 끝 (뒤로 빠지거나 되돌아 돌지 않는다)
                elif side:  # 옆걸음한 만큼 빠지고 원래 방향으로
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
            self._set("done", "완료" + (" (트레이에 물건이 남아 있을 수 있음)" if self.state.get("tray_left") else ""))
        except NavError as e:
            await self._stop()
            self._set("failed", str(e))
        except asyncio.CancelledError:
            await self._stop()
            raise

    async def _go_with_retries(self, station: str) -> None:
        """목표 마커까지 간다. 실패하면 (줄 따라가기: 전진한 만큼 뒤로 물러나) 처음 자리에서 마커를 다시 찾는다."""
        self._net = 0
        if self.cfg.pan_look:  # pan_look 은 앞뒤로 훑는 것을 스스로 한다 (되돌아가며 후진 확인)
            await self._go(station)
            return
        for attempt in range(self.cfg.fail_retries + 1):
            try:
                await self._go(station)
                return
            except NavError as e:
                if attempt >= self.cfg.fail_retries:
                    raise
                label = self.stations[station]["label"]
                self._set("search", f"{label} 못 찾음 ({e}) → 다시 마커를 찾으러 갑니다 ({attempt + 1}/{self.cfg.fail_retries})")
                if self.cfg.row_mode:
                    for _ in range(max(0, self._net)):
                        await self._pulse("backward", self.cfg.speed, self.cfg.pulse_ms)
                    self._net = 0
                await self._stop()

    async def _dump_with_tray(self, label: str) -> None:
        """샤오 카메라로 트레이를 보고 쏟는다: 쏟기 전에 물건이 떨어질 위치인지, 쏟은 뒤에 비었는지 (안 비면 최대 2번 더)."""
        tray = getattr(self.robot, "tray", None)
        if tray is not None and tray.ready:
            st = None
            for _ in range(6):  # 물건이 아직 흔들리며 자리 잡는 중일 수 있어 최대 약 5초 기다린다
                st = await asyncio.to_thread(tray.look)
                if st is None or not st["present"] or st["in_zone"]:
                    break
                await self.sleep(1)
            if st is not None and not st["present"]:
                self._set("dumping", "샤오 카메라: 트레이가 비어 있어 쏟지 않음")
                return
            if st is not None and not st["in_zone"]:
                raise NavError("샤오 카메라: 물건이 쏟으면 떨어질 위치에 있지 않습니다")
        sorter = getattr(self.robot, "sorter", None)
        for attempt in range(3):  # 처음 한 번 + 안 비면 2배속으로 최대 2번 더
            fast = attempt > 0
            speed = 2.0 ** attempt  # 안 비면 이전보다 2배 빠르게: 1배 → 2배 → 4배
            self._set("dumping", f"{label} 에 쏟는 중" + (f" (안 비어서 {speed:g}배속으로 다시 {attempt}번째)" if fast else ""))
            if fast:
                await asyncio.to_thread(self.robot.driver.dump, speed)
            else:
                await asyncio.to_thread(self.robot.driver.dump)
            if self._board_judges():  # 샤오 판정 영상에서 '비어있음'이 확인되면 끝
                if await self._wait_empty(sorter):
                    return
            elif tray is not None and tray.ready:  # 사진 비교 방식 (판정 영상 대신 사진 모드일 때)
                await self.sleep(0.8)
                st = await asyncio.to_thread(tray.look)
                if st is None or not st["present"]:
                    return
            else:
                return
        self.state["tray_left"] = True
        self._set("dumping", "샤오 카메라: 2배속으로 다시 쏟아도 트레이가 비지 않음")

    def _board_judges(self) -> bool:
        """샤오가 판정 영상(USB)을 보내고 있나"""
        board = getattr(self.robot, "board", None)
        reads = bool(getattr(board, "enabled", False)) or getattr(self.robot, "judge", None) is not None
        return getattr(self.robot, "sorter", None) is not None and reads

    async def _wait_empty(self, sorter, timeout: float = 15.0) -> bool:
        """쏟기가 끝난 뒤에 찍은 샤오 프레임으로 트레이가 비었는지 본다 (모델이 3~4초에 한 장). 빈 트레이면 True, 물건이 보이면 False.
        시간 안에 프레임이 안 오면(보드 이상) 계속 쏟아 봐야 소용없으니 비었다고 본다."""
        import time
        t_end = time.monotonic()
        waited = 0.0
        while waited < timeout:
            r = sorter.empty_after(t_end)
            if r is not None:
                return r
            await self.sleep(0.5)
            waited += 0.5
        return True

    async def _pulse(self, action: str, speed: int, ms: int) -> None:
        self.moves.append((time.strftime("%H:%M:%S"), action, ms))
        print(f"[mission] {action} {ms}ms", flush=True)
        self.robot.move(action, speed, ms + 300)  # 서버 자동 정지는 여유 있게, 실제 정지는 여기서
        if self.robot.blocked:
            raise NavError("앞에 장애물이 있어 멈췄습니다")
        await self.sleep(ms / 1000)
        await self._stop()
        await self.sleep(self.cfg.settle_ms / 1000)
        self.heading += self._turn_deg(action, ms)
        self._net += {"forward": 1, "backward": -1}.get(action, 0)

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

    async def _look(self) -> list[Marker]:
        """사진 몇 장을 보고 합친다. 같은 번호는 가장 크게 보인 것 하나, 후보 네모는 전부."""
        found: dict[int, Marker] = {}
        cands: list[Marker] = []
        for k in range(self.cfg.look_frames):
            if k:
                await self.sleep(self.cfg.look_gap_ms / 1000)
            for m in await asyncio.to_thread(self.robot.vision.markers):
                if m.id == CANDIDATE:
                    cands.append(m)
                elif m.id not in found or m.size > found[m.id].size:
                    found[m.id] = m
        self.seen = sorted(list(found.values()) + cands, key=lambda m: -m.size)
        return self.seen

    def _bearing(self, m: Marker) -> float:
        return self.heading - m.cx * self.cfg.half_fov_deg  # cx + = 화면 오른쪽 = 방향 −

    async def _scan(self, info: dict) -> list[dict]:
        """몸을 한 바퀴 돌며 보이는 블록을 기록. 목표가 보이면 그 자리에서 멈춘다 (목표를 보고 있음)."""
        cfg, target = self.cfg, info["marker"]
        self._set("scan", f"{info['label']} (마커 {target}) 한 바퀴 둘러보는 중")
        start, sightings = self.heading, []
        while True:
            await self._look()
            for m in self.seen:
                sightings.append({"id": m.id, "bearing": self._bearing(m), "size": m.size})
            if any(m.id == target for m in self.seen) or abs(self.heading - start) >= 360:
                return sightings
            before = self.heading
            await self._pulse("turn_left", cfg.turn_speed, cfg.scan_step_ms)
            if self.heading == before:  # 각도 설정이 이상하면 끝없이 돌지 않게
                return sightings
            await self.sleep(cfg.scan_pause_ms / 1000)  # 멈춰서 화면이 안정된 뒤 마커 찾기 (다음 반복의 _look)

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
                await self._look()
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
            await self._look()
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
            await self._look()
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
                await self._look()
                if any(m.id == info["marker"] for m in self.seen):
                    found = -1.0 if pan > 90 else 1.0  # 각도가 크면 왼쪽을 보고 있다
                    break
        finally:
            await asyncio.to_thread(self.robot.driver.set_servo, 90, None)  # 다시 정면
            await self.sleep(self.cfg.look_settle_ms / 1000)
        return found

    async def _go_row(self, name: str) -> None:
        """줄 따라가기: 마커를 일렬로 세워 둔 곳에서 회전 없이 목표 번호 마커 앞까지 간다.
        - 목표가 보이면: 한쪽으로 치우쳤으면 옆으로 이동(몸을 돌리지 않는다) → 가운데면 전진 → 가까워지면 도착, 너무 가까우면 후진
        - 목표가 안 보이면: 보일 때까지 앞으로 전진 (마커 줄 바로 앞인데도 목표 번호가 없으면 멈춘다)"""
        cfg, info = self.cfg, self.stations[name]
        target = info["marker"]
        self.state["target"] = name
        side = cfg.side_camera
        step_ms = cfg.side_step_ms if side and cfg.side_step_ms else cfg.pulse_ms
        ref_size, fixes = None, 0  # 줄을 따라 갈 때 기준이 되는 마커 크기(처음 본 것), 간격을 되돌린 횟수
        seen_cx, lost = None, 0  # 목표 마커를 마지막으로 본 가로 위치, 그 뒤 연속으로 못 본 횟수
        back_size = cfg.back_size or cfg.arrive_size * 1.8
        last_size, advance = 0.0, 0
        for _ in range(cfg.step_limit):
            await self._look()
            self.state["steps"] += 1
            m = next((x for x in self.seen if x.id == target), None)
            if m is not None:
                seen_cx, lost = m.cx, 0
            if m is None:
                if last_size >= cfg.arrive_size * cfg.lost_near:
                    # 바로 전 걸음에 크게 보였는데 사라짐 = 너무 가까워 화면 밖(카메라가 낮아 마커가 아래로 빠짐) → 도착
                    self._set("arrived", f"{info['label']} (마커 {target}) 가까워서 안 보임 → 도착")
                    await self._stop()
                    return
                last_size = 0.0
                if side and seen_cx is not None:  # 방금 보이던 목표를 놓쳤다 → 지나치지 말고 마지막으로 본 쪽으로 한 걸음씩 돌아가 다시 본다
                    lost += 1
                    if lost > 2:
                        seen_cx = None
                    else:
                        self._set("align", f"{info['label']} (마커 {target}) 잠깐 놓침 → 마지막으로 본 쪽으로 다시 확인")
                        await self._pulse("forward" if seen_cx > 0 else "backward", cfg.speed, step_ms)
                        continue
                near = [x for x in self.seen if x.id != CANDIDATE and x.size >= cfg.arrive_size and abs(x.cx) <= cfg.arrive_cx]
                if near and not side:  # 정면에 다른 번호 마커가 바로 앞인데 목표가 없다 → 더 가면 부딪힌다 (옆에 비켜 있는 마커는 그냥 지나간다)
                    ids = sorted({x.id for x in near})
                    raise NavError(f"{info['label']} 마커 줄 바로 앞인데 마커 {target} 번이 안 보입니다 (보이는 번호 {ids})")
                row = [x for x in self.seen if x.id != CANDIDATE]
                if side and cfg.side_hold and row:  # 줄 옆 마커들은 같은 크기로 보여야 한다 → 크기가 달라지면 길이 휘어 줄에서 멀어지거나 가까워진 것
                    ref = min(row, key=lambda x: abs(x.cx))
                    if ref_size is None:
                        ref_size = ref.size
                    elif fixes < cfg.side_hold_max and abs(ref.size - ref_size) > cfg.side_hold * ref_size:
                        fixes += 1
                        away = ref.size < ref_size       # 작아졌다 = 줄에서 멀어짐 → 오른쪽(줄 쪽)으로
                        self._set("align", f"길이 {'줄에서 멀어져' if away else '줄에 가까워져'} {'오른쪽' if away else '왼쪽'}으로 되돌리는 중 ({fixes}/{cfg.side_hold_max})")
                        await self._pulse("strafe_right" if away else "strafe_left", cfg.speed, step_ms)
                        continue
                if advance >= cfg.line_advance_steps:
                    raise NavError(f"{info['label']} 앞으로 {advance}걸음 가며 찾았지만 마커 {target} 번이 안 보입니다. "
                                   "마커를 일렬로, 카메라가 볼 수 있게 놓아 주세요")
                advance += 1
                others = sorted({x.id for x in self.seen if x.id != CANDIDATE})
                self._set("search", f"{info['label']} (마커 {target}) " + (f"마커 {others} 는 아님 → " if others else "")
                          + f"앞으로 한 걸음 가서 다시 확인 ({advance}/{cfg.line_advance_steps})")
                await self._pulse("forward", cfg.speed, step_ms)
                continue
            cm = 0 if side else await asyncio.to_thread(self.robot.driver.distance_cm)  # 옆 카메라면 앞쪽 초음파는 쓸모없다
            centered = abs(m.cx) <= cfg.center_tol
            if side and centered and not cfg.side_approach:  # 옆 카메라: 마커 바로 앞(줄 방향으로 마주 봄)에 서면 멈춰서 쏟는다
                self._set("arrived", f"{info['label']} (마커 {target}) 바로 앞")
                await self._stop()
                return
            if (cfg.arrive_size <= m.size < back_size and abs(m.cx) <= cfg.arrive_cx) or (centered and 0 < cm <= cfg.arrive_cm):
                self._set("arrived", f"{info['label']} (마커 {target})")
                await self._stop()
                return
            last_size = m.size
            if side:  # 오른쪽을 보는 카메라: 화면 오른쪽 = 로봇 앞쪽 (실측: 후진하면 마커가 화면 오른쪽으로 간다)
                if not centered:
                    self._set("align", f"{info['label']} (마커 {target}) 줄 따라 {'전진' if m.cx > 0 else '후진'}해 맞추는 중")
                    await self._pulse("forward" if m.cx > 0 else "backward", cfg.speed, step_ms)
                elif m.size >= back_size:
                    self._set("approach", f"{info['label']} (마커 {target}) 너무 가까워 왼쪽으로")
                    await self._pulse("strafe_left", cfg.speed, cfg.pulse_ms)
                else:
                    self._set("approach", f"{info['label']} (마커 {target}) 오른쪽으로 다가가는 중")
                    await self._pulse("strafe_right", cfg.speed, cfg.pulse_ms)
            elif m.size >= back_size:  # 너무 가까움 → 후진
                self._set("approach", f"{info['label']} (마커 {target}) 너무 가까워 후진")
                await self._pulse("backward", cfg.speed, cfg.pulse_ms)
            elif not centered:  # 몸은 돌리지 않고 옆으로 이동해 마커를 가운데로
                self._set("align", f"{info['label']} (마커 {target}) 옆으로 이동해 가운데로")
                await self._pulse("strafe_right" if m.cx > 0 else "strafe_left", cfg.speed, cfg.pulse_ms)
            else:
                self._set("approach", f"{info['label']} (마커 {target})")
                await self._pulse("forward", cfg.speed, cfg.pulse_ms)
        raise NavError(f"{info['label']} 까지 너무 오래 걸립니다 (걸음 {cfg.step_limit} 초과)")

    async def _go_pan_look(self, name: str) -> None:
        """일직선 전진·후진만 (회전·옆걸음·한 바퀴 돌기 없음). 한 걸음마다 멈춰 카메라를 오른쪽(scan_pan)으로 돌려 마커를 확인한다.
        목표 마커가 보이면 바로 멈춰 쏟고, 아니면 카메라를 정면으로 돌리고 한 걸음. 줄 끝까지 가도 없으면 몸을 돌리지 않고 *후진*하며 같은 방법으로
        다시 확인한다 (카메라는 계속 오른쪽 마커 줄을 본다). 앞으로(line_advance_steps)·뒤로(출발점 + pan_back_margin) 번갈아 최대 fail_retries+1 번 훑는다."""
        cfg, info = self.cfg, self.stations[name]
        target = info["marker"]
        self.state["target"] = name
        net = aligns = lost = 0   # net = 출발점에서 앞으로 간 걸음 수 (뒤로 가면 줄어든다)
        seen_cx = None
        direction = 1             # +1 전진, -1 후진
        cur_pan = None            # 지금 카메라가 향한 각도 (같으면 서보를 다시 움직이지 않는다)
        judged: set = set()       # 이미 멈춰서 판단한 마커 번호
        target_net = None         # 다른 마커 때문에 못 쏟고 지나친 목표를 본 위치(net). 다른 마커를 다 지나면 그 위치로 돌아간다
        returns = 0
        passes = 1
        returning = False        # 목표를 봤던 자리로 돌아가는 중이면 다른 마커가 다시 보여도 목표가 보이는 순간 쏟는다
        for _ in range(cfg.step_limit):
            self._set("search" if seen_cx is None else "align", f"{info['label']} (마커 {target}) 멈춰서 오른쪽을 보고 확인 중")
            if cur_pan != cfg.scan_pan:  # 카메라가 이미 마커 줄을 보고 있으면 다시 돌리지 않는다 (전진·후진만으로 찾는다)
                await asyncio.to_thread(self.robot.driver.set_servo, cfg.scan_pan, None)
                cur_pan = cfg.scan_pan
                if cfg.scan_pause_ms:
                    await self.sleep(cfg.scan_pause_ms / 1000)  # 돌아간 화면이 안정되고 마커를 알아볼 때까지 멈춰 있는다
            await self._look()
            self.state["steps"] += 1
            m = next((x for x in self.seen if x.id == target), None)
            fresh = sorted({x.id for x in self.seen if x.id != CANDIDATE and x.id != target and x.id not in judged})
            if fresh:  # 목표가 아닌 마커가 처음 보임 → 멈춘 채 판단을 보여 주고 (트레이와 다름) 그다음 전진
                judged.update(fresh)
                self._set("search", f"마커 {fresh} 번이 보임 → 트레이는 {info['label']}(마커 {target}) → 다른 마커라 지나감")
                await self.sleep(cfg.pan_judge_ms / 1000)
            # 목표가 보여도, 목표가 아닌 마커가 아직 옆에 (비슷한 크기로) 있으면 그 마커를 다 지날 때까지 쏟지 않고 간다
            alongside = [x for x in self.seen if m is not None and x.id != target and x.id != CANDIDATE and x.size >= 0.6 * m.size]
            blocking = bool(alongside) and not returning
            if blocking:
                target_net = net  # 목표를 본 위치를 기억해 두고, 다른 마커가 시야에서 빠지면 그 위치로 돌아가 쏟는다
                returns = 0
                m = None
                self._set("search", f"마커 {sorted({x.id for x in alongside})} 번이 아직 옆에 있음 → 다 지난 뒤에 {info['label']}(마커 {target}) 에 쏟는다")
            if m is not None:
                seen_cx, lost = m.cx, 0
                if not cfg.pan_center or abs(m.cx) <= cfg.center_tol:
                    self._set("arrived", f"{info['label']} (마커 {target}) 보여서 멈춤 → 트레이와 같은 마커라 쏟는다")
                    await self._stop()
                    return
                if aligns >= cfg.pan_align_max:
                    raise NavError(f"{info['label']} 마커 {target} 번을 가운데에 맞추지 못했습니다")
                aligns += 1
                self._set("align", f"{info['label']} (마커 {target}) 줄 방향으로 {'전진' if m.cx > 0 else '후진'}해 맞추는 중")
                await self._pulse("forward" if m.cx > 0 else "backward", cfg.speed, cfg.pan_align_ms)
                net += 1 if m.cx > 0 else -1
                continue
            other_in_view = any(x.id != target and x.id != CANDIDATE for x in self.seen)
            if target_net is not None and not blocking and (returning or not other_in_view):  # 다른 마커가 시야에서 다 빠진 뒤에만 돌아간다
                if net != target_net and returns < 3:  # 다른 마커를 다 지났는데 목표가 안 보임 → 목표를 봤던 위치로 걸음 수만큼 돌아간다
                    returns += 1
                    returning = True
                    step = -1 if net > target_net else 1
                    self._set("align", f"다른 마커를 다 지남 → {info['label']}(마커 {target}) 를 봤던 자리로 {'후진' if step < 0 else '전진'}")
                    await self._pulse("forward" if step > 0 else "backward", cfg.speed, cfg.pan_step_ms)
                    net += step
                    continue
                target_net, returning = None, False
            if seen_cx is not None and lost < 2 and not blocking:  # 방금 보이던 목표를 놓침 → 지나쳤으니 마지막으로 본 쪽으로 한 걸음 돌아가 다시 본다
                lost += 1
                await self._pulse("forward" if seen_cx > 0 else "backward", cfg.speed, cfg.pan_align_ms)
                net += 1 if seen_cx > 0 else -1
                continue
            if not blocking:
                seen_cx = None
            others = sorted({x.id for x in self.seen if x.id != CANDIDATE})
            end = net >= cfg.line_advance_steps if direction > 0 else net <= -cfg.pan_back_margin
            if end:  # 이 방향 끝 → 몸을 돌리지 않고 반대(후진/전진)로 같은 방법으로 다시 훑는다
                if passes > cfg.fail_retries:
                    raise NavError(f"{info['label']} 앞뒤로 훑으며 확인했지만 마커 {target} 번이 안 보입니다. 마커를 카메라가 볼 수 있게 놓아 주세요")
                passes += 1
                direction = -direction
                self._set("search", f"{info['label']} (마커 {target}) 줄 끝까지 없음 → {'전진' if direction > 0 else '후진'}하며 다시 확인 ({passes}/{cfg.fail_retries + 1})")
            self._set("search", f"{info['label']} (마커 {target}) " + (f"마커 {others} 는 아님 → " if others else "")
                      + f"{'앞' if direction > 0 else '뒤'}로 한 걸음 (위치 {net})")
            if cur_pan != cfg.travel_pan:  # travel_pan 이 scan_pan 과 같으면 카메라는 움직이지 않는다
                await asyncio.to_thread(self.robot.driver.set_servo, cfg.travel_pan, None)
                cur_pan = cfg.travel_pan
            try:
                await self._pulse("forward" if direction > 0 else "backward", cfg.speed, cfg.pan_step_ms)
            except NavError:
                if direction > 0 and passes <= cfg.fail_retries:  # 앞이 막혔다 = 줄의 끝. 실패로 끝내지 말고 후진하며 다시 훑는다
                    await self._stop()
                    self._set("search", f"{info['label']} 앞이 막힘 → 줄 끝으로 보고 후진하며 다시 확인")
                    net = cfg.line_advance_steps
                    continue
                raise
            net += direction
        raise NavError(f"{info['label']} 까지 너무 오래 걸립니다 (걸음 {cfg.step_limit} 초과)")

    async def _go(self, name: str) -> None:
        if self.cfg.pan_look:
            await self._go_pan_look(name)
            return
        if self.cfg.row_mode:
            return await self._go_row(name)
        cfg, info = self.cfg, self.stations[name]
        target = info["marker"]
        self.state["target"] = name
        last_size, looked, sightings, done, went_back = 0.0, False, None, [], False
        rescans_left = cfg.rescans
        ahead_tried = False
        advance_steps = 0
        for _ in range(cfg.step_limit):
            await self._look()
            self.state["steps"] += 1
            m = next((m for m in self.seen if m.id == target), None)
            if m is None:
                if last_size >= cfg.arrive_size * cfg.lost_near:
                    # 바로 전 걸음에 크게 보였는데 사라짐 = 너무 가까워 화면 밖 (카메라가 정면 고정이라 낮은 마커는 아래로 빠진다)
                    self._set("arrived", f"{info['label']} (마커 {target}) 가까워서 안 보임 → 도착")
                    await self._stop()
                    return
                last_size = 0.0
                if not ahead_tried:  # 0) 번호는 못 읽었지만 마커처럼 생긴 네모가 앞에 보이면, 돌아보기 전에 먼저 그쪽으로 다가가 번호를 읽는다
                    ahead_tried = True
                    cands = [c for c in self.seen if c.id == CANDIDATE and abs(c.cx) < cfg.ahead_cx]
                    if cands:
                        best = max(cands, key=lambda c: c.size)  # 가장 크게 보이는(가까운) 네모
                        bearing = self._bearing(best)
                        done.append(bearing)  # 가 본 방향은 나중에 미식별 블록 후보에서 뺀다
                        self._set("visit", f"{info['label']} (마커 {target}) 앞에 보이는 마커 후보로 다가가는 중")
                        await self._visit(info, bearing)  # 번호가 읽혀 목표면 목표를 보는 채로 돌아온다 → 다음 반복에서 바로 접근
                        continue
                if not looked:  # 1) 카메라만 둘러보기 → 보이면 그쪽으로 한 번 회전
                    looked = True
                    side = await self._look_around(info)
                    if side is not None:
                        await self._pulse("turn_right" if side > 0 else "turn_left", cfg.turn_speed, cfg.turn90_ms // 2)
                    continue
                if cfg.line_mode:  # 마커 줄이 안 보이면 몸으로 돌지 않고 앞으로 전진하며 스캔한다
                    near = [x for x in self.seen if x.id != CANDIDATE and x.size >= cfg.arrive_size]
                    if near:  # 마커 줄 바로 앞인데도 목표 번호가 없다 → 더 가면 부딪힌다
                        ids = sorted({x.id for x in near})
                        raise NavError(f"{info['label']} 마커 줄 바로 앞인데 마커 {target} 번이 안 보입니다 (보이는 번호 {ids})")
                    if advance_steps >= cfg.line_advance_steps:
                        raise NavError(f"{info['label']} 앞으로 {advance_steps}걸음 가며 찾았지만 마커 {target} 번이 안 보입니다. "
                                       "마커를 일렬로, 카메라가 볼 수 있게 놓아 주세요")
                    advance_steps += 1
                    self._set("search", f"{info['label']} (마커 {target}) 앞으로 전진하며 마커 줄 찾는 중 ({advance_steps}/{cfg.line_advance_steps})")
                    await self._pulse("forward", cfg.speed, cfg.pulse_ms)
                    if advance_steps % 5 == 0:
                        looked = False  # 5걸음마다 카메라로 다시 좌우를 둘러본다
                    continue
                if sightings is None:  # 2) 몸으로 한 바퀴만
                    sightings = await self._scan(info)
                    continue
                seen_target = [x for x in sightings if x["id"] == target]
                if seen_target and not went_back:  # 한 바퀴 중에 목표를 봤으면 그 방향으로
                    went_back = True
                    await self._turn_to(max(seen_target, key=lambda x: x["size"])["bearing"])
                    continue
                todo = self._unknowns(sightings, target, done)  # 3) 미확인 블록 하나씩
                if not todo:
                    if rescans_left > 0:  # 번호가 맞는 블록은 반드시 있으니, 식별된 블록은 빼고 처음부터 다시 둘러본다
                        rescans_left -= 1
                        sightings, done, went_back = None, [], False
                        continue
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
