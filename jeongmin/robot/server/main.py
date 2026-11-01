"""라즈봇 웹 조종 서버.

라즈베리파이:  ~/raspbot-venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
노트북(가짜):  ROBOT_MODE=fake uvicorn server.main:app --port 8000
→ 브라우저로 http://<주소>:8000 , API 문서는 /docs

안전장치
- 모든 이동 명령은 duration_ms 뒤에 자동으로 멈춘다 (기본 500ms, 최대 3000ms).
  계속 움직이려면 화면처럼 0.2초마다 같은 명령을 다시 보낸다 → 연결이 끊기면 로봇이 알아서 선다.
- 속도는 MAX_SPEED (기본 150 / 255) 를 넘지 않는다.
- 리모컨 비상 정지: IR_STOP_KEY 버튼(기본 0 = 전원 버튼)을 누르면 바퀴 정지 + 임무 취소. none 이면 끔.
- 앞쪽으로 가는 중에 초음파 거리가 OBSTACLE_CM (기본 15cm) 보다 가까우면 멈추고,
  그 상태에서는 앞쪽 이동 명령을 받지 않는다 (뒤·옆·회전은 된다). 0 이면 끔.

통 찾아가기 (stations.json 의 정류장마다 ArUco 마커):
  키트 블록(AprilTag 1~4번)으로 하려면 STATIONS_FILE=stations.blocks.json
  POST /api/mission {"station": "can"} → 마커 찾아 다가가기 → 쏟기 → 출발점(home) 복귀
  수동 이동·정지 명령이 오면 임무는 바로 취소된다.

AI 판정 (분류 보드 → USB, 또는 POST /api/verdict) — sorter.py:
  {"class":"can","conf":0.93} 이 오고 자동 출발이 켜져 있으면 can 통 임무를 시작한다.
  자동 출발은 기본 꺼짐 (AUTO_SORT=1 또는 POST /api/sort {"auto": true}). 처리 기록은 GET /api/history.
  BOARD_PORT=auto|none|/dev/ttyACM0  (실제 로봇 기본 auto, 가짜 모드 기본 none)
  HISTORY_FILE=기록 파일 경로|none    (실제 로봇 기본 data/history.jsonl, 가짜 모드 기본 none)

다른 웹(팀원 화면)에서 브라우저로 API 를 부르려면 CORS_ORIGINS 에 그 웹 주소를 쉼표로 적는다.
  예) CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5500"   (비워 두면 이 서버의 화면만 허용)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .board import BoardReader
from .board_cam import BoardCamera
from .tray_check import TrayCheck
from .camera import Camera
from .drivers import IR_POWER, LED_COLORS, MOVES, PAN_RANGE, TILT_RANGE, make_driver
from .navigator import Mission, NavConfig
from .sorter import Sorter, parse_line
from .vision import MARKER_DICT, CameraVision, NoVision, SimVision, decoded

MAX_SPEED = int(os.environ.get("MAX_SPEED", "150"))
OBSTACLE_CM = float(os.environ.get("OBSTACLE_CM", "15"))
_ir_stop = os.environ.get("IR_STOP_KEY", str(IR_POWER)).lower()
IR_STOP_KEY = None if _ir_stop == "none" else int(_ir_stop)
FORWARD_MOVES = {"forward", "diag_forward_left", "diag_forward_right"}  # 초음파 센서는 앞에 있다
# 끝의 / 는 브라우저가 보내는 Origin 에 없으므로 떼어 둔다
CORS_ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
STATIC = Path(__file__).parent / "static"
STATIONS_FILE = Path(os.environ.get("STATIONS_FILE", Path(__file__).parent.parent / "stations.json"))
_CONF = json.loads(STATIONS_FILE.read_text(encoding="utf-8"))
STATIONS: dict = _CONF["stations"]
STATIONS_MARKER_DICT = _CONF.get("marker_dict", MARKER_DICT)
NAV = NavConfig.from_dict(_CONF.get("nav", {}))
MIN_CONFIDENCE = float(_CONF.get("sort", {}).get("min_confidence", 0.8))
DEFAULT_HISTORY = Path(__file__).parent.parent / "data" / "history.jsonl"


def _setting(name: str, real_default: str, fake: bool) -> str:
    return os.environ.get(name, "none" if fake else real_default)


class Robot:
    """드라이버 + 카메라 + 자동 정지 타이머"""

    def __init__(self) -> None:
        self.driver = make_driver()
        self.camera = Camera()
        if self.driver.mode == "fake":
            self.vision = SimVision(self.driver.world)  # 가짜 세계의 마커
        elif self.camera.kind != "none":
            self.vision = CameraVision(self.camera, STATIONS_MARKER_DICT)
        else:
            self.vision = NoVision()
        self.mission = Mission(self, STATIONS, NAV)
        fake = self.driver.mode == "fake"
        history = _setting("HISTORY_FILE", str(DEFAULT_HISTORY), fake)
        self.sorter = Sorter(self, STATIONS, MIN_CONFIDENCE, auto=os.environ.get("AUTO_SORT") == "1",
                             history_file=None if history.lower() == "none" else Path(history))
        self.board = BoardReader(_setting("BOARD_PORT", "auto", fake), self._on_board_line)
        # 판정을 안 읽을 때(BOARD_PORT=none)만 보드 카메라 사진을 USB 로 받아 본다 (사진 수집용 펌웨어일 때)
        self.board_cam = None if fake or self.board.enabled else BoardCamera(os.environ.get("BOARD_CAM_PORT", "auto"))
        self.tray = TrayCheck(self.board_cam, Path(__file__).parent.parent / "tray_empty.jpg", _CONF.get("tray")) if self.board_cam else None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_at = 0.0
        self._watchdog: asyncio.Task | None = None
        self.blocked = False  # 장애물 때문에 멈췄는지

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._watchdog = asyncio.create_task(self._watch())
        self.board.start()

    def _on_board_line(self, line: str) -> None:
        """보드 읽기 스레드에서 불린다 → 판정 처리는 이벤트 루프로 넘긴다"""
        obj = parse_line(line)
        if obj is not None and self._loop:
            self._loop.call_soon_threadsafe(self.sorter.handle, obj, "board")

    async def _watch(self) -> None:
        tick = 0
        while True:
            await asyncio.sleep(0.05)
            tick += 1
            if IR_STOP_KEY is not None and await asyncio.to_thread(self.driver.remote_key) == IR_STOP_KEY:
                print("[robot] 리모컨 비상 정지")
                await self.mission.abort("리모컨 정지")
                await asyncio.to_thread(self.driver.stop)
                continue
            moving = self.driver.state.moving
            if moving and time.monotonic() >= self._stop_at:
                await asyncio.to_thread(self.driver.stop)
            elif moving in FORWARD_MOVES and tick % 2 == 0:  # 0.1초마다 앞 거리 확인
                if await asyncio.to_thread(self.too_close):
                    self.blocked = True
                    await asyncio.to_thread(self.driver.stop)

    def too_close(self) -> bool:
        if OBSTACLE_CM <= 0:
            return False
        cm = self.driver.distance_cm()
        return 0 < cm < OBSTACLE_CM  # 0 이하는 측정 실패로 보고 무시

    def move(self, action: str, speed: int, duration_ms: int) -> None:
        if action in FORWARD_MOVES and self.too_close():
            self.blocked = True
            self.driver.stop()
            return
        self.blocked = False
        self.driver.move(action, min(speed, MAX_SPEED))
        self._stop_at = time.monotonic() + duration_ms / 1000

    def close(self) -> None:
        self.board.stop()
        if self._watchdog:
            self._watchdog.cancel()
        self.driver.close()
        self.camera.close()
        if self.board_cam:
            self.board_cam.close()


robot: Robot | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global robot
    robot = Robot()
    await robot.start()
    print(f"[robot] mode={robot.driver.mode} camera={robot.camera.kind} max_speed={MAX_SPEED} "
          f"cors={CORS_ORIGINS or '없음'} board={robot.board.want} auto_sort={robot.sorter.auto}")
    yield
    await robot.mission.abort("서버 종료")
    robot.close()


app = FastAPI(title="Raspbot 조종 서버", lifespan=lifespan)
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

MoveAction = Literal[tuple(MOVES)]  # forward, backward, turn_left, ... (drivers.MOVES 참고)


class MoveIn(BaseModel):
    action: MoveAction  # type: ignore[valid-type]
    speed: int = Field(default=100, ge=0, le=255, description=f"0~255, MAX_SPEED({MAX_SPEED}) 를 넘으면 잘림")
    duration_ms: int = Field(default=500, ge=50, le=3000, description="이 시간이 지나면 자동으로 멈춤")


class ServoIn(BaseModel):
    pan: int | None = Field(default=None, ge=PAN_RANGE[0], le=PAN_RANGE[1], description="좌우 0~180, 90 이 정면, 커질수록 왼쪽 (실측)")
    tilt: int | None = Field(default=None, ge=TILT_RANGE[0], le=TILT_RANGE[1], description="위아래 0~110")


class BeepIn(BaseModel):
    ms: int = Field(default=150, ge=10, le=2000)


class LedIn(BaseModel):
    color: Literal[tuple(LED_COLORS)] | None = None  # type: ignore[valid-type]  None 이면 끔


class MissionIn(BaseModel):
    station: Literal[tuple(STATIONS)]  # type: ignore[valid-type]  stations.json 의 이름
    dump: bool = Field(default=True, description="도착하면 쏟기")
    return_home: bool = Field(default=True, description="끝나면 출발점(home)으로")


class SortIn(BaseModel):
    auto: bool = Field(description="AI 판정이 오면 자동으로 출발할지")


class ResetIn(BaseModel):
    station: Literal[tuple(n for n in STATIONS if n != "home")] | None = None  # type: ignore[valid-type]  None 이면 모든 통


@app.get("/api/status")
def status():
    s = robot.driver.state
    return {"mode": s.mode, "moving": s.moving, "speed": s.speed, "pan": s.pan, "tilt": s.tilt,
            "led": s.led, "camera": robot.camera.kind, "max_speed": MAX_SPEED,
            "blocked": robot.blocked, "obstacle_cm": OBSTACLE_CM, "mission": robot.mission.state["phase"],
            "auto_sort": robot.sorter.auto}


@app.post("/api/move")
async def move(body: MoveIn):  # 임무 취소가 이벤트 루프에서 돌아야 해서 async
    await robot.mission.abort("수동 조종")
    robot.move(body.action, body.speed, body.duration_ms)
    return status()


@app.post("/api/stop")
async def stop():
    await robot.mission.abort("정지 버튼")
    robot.driver.stop()
    return status()


@app.post("/api/servo")
def servo(body: ServoIn):
    robot.driver.set_servo(body.pan, body.tilt)
    return status()


@app.get("/api/distance")
def distance():
    return {"cm": robot.driver.distance_cm()}


@app.get("/api/line")
def line():
    return {"sensors": robot.driver.line(), "order": "왼쪽 → 오른쪽"}


@app.post("/api/beep")
def beep(body: BeepIn):
    robot.driver.beep(body.ms)
    return {"ok": True}


@app.post("/api/led")
def led(body: LedIn):
    robot.driver.set_led(body.color)
    return status()


@app.get("/api/stations")
def stations():
    return STATIONS


@app.get("/api/markers")
async def markers():
    """지금 카메라에 보이는 마커 (가짜 모드면 가짜 세계의 위치도)"""
    seen = await asyncio.to_thread(robot.vision.markers)
    out = {"markers": [m.to_dict() for m in decoded(seen)]}
    if robot.driver.mode == "fake":
        out["pose"] = robot.driver.world.pose()
    return out


@app.post("/api/mission", status_code=202)
async def mission_start(body: MissionIn):
    if robot.mission.running:
        raise HTTPException(status_code=409, detail="이미 임무 중입니다. 먼저 /api/mission/cancel")
    robot.sorter.start(body.station, by="web", dump=body.dump, return_home=body.return_home)
    return robot.mission.state


@app.get("/api/mission")
def mission_state():
    cur = robot.sorter.current or {}
    return {**robot.mission.state, "running": robot.mission.running,
            "seen": [m.to_dict() for m in decoded(robot.mission.seen)],
            "label": cur.get("label"), "confidence": cur.get("confidence"), "by": cur.get("by")}


@app.post("/api/mission/cancel")
async def mission_cancel():
    await robot.mission.abort()
    return mission_state()


@app.post("/api/verdict")
async def verdict(obj: dict = Body(..., examples=[{"class": "can", "conf": 0.93, "ms": 173}])):
    """보드와 같은 판정 JSON 을 HTTP 로 넣는다 (시험용, 또는 다른 분류기)"""
    return robot.sorter.handle(obj, source="api")


@app.get("/api/sort")
def sort_state():
    return {"auto": robot.sorter.auto, "min_confidence": robot.sorter.min_confidence,
            "board": robot.board.status(), "last_verdict": robot.sorter.last_verdict}


@app.post("/api/sort")
def sort_set(body: SortIn):
    robot.sorter.auto = body.auto
    return sort_state()


@app.get("/api/history")
def history():
    return robot.sorter.history()


@app.post("/api/history/reset")
def history_reset(body: ResetIn):
    robot.sorter.reset(body.station)
    return robot.sorter.history()


@app.get("/api/camera.jpg")
def camera_jpg():
    data = robot.camera.jpeg()
    if data is None:
        raise HTTPException(status_code=503, detail="카메라가 없습니다 (CAMERA 환경변수, 케이블 확인)")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/stream")
def stream():
    if robot.camera.kind == "none":
        raise HTTPException(status_code=503, detail="카메라가 없습니다")
    return StreamingResponse(robot.camera.frames(), media_type="multipart/x-mixed-replace; boundary=frame")


def _board_cam():
    if robot.board_cam is None:
        raise HTTPException(status_code=503, detail="보드 카메라를 쓰지 않습니다 (판정 읽기 중이거나 가짜 모드). BOARD_PORT=none 으로 켜면 사진 수집용 펌웨어의 사진을 볼 수 있습니다")
    return robot.board_cam


@app.get("/api/board/camera.jpg")
def board_camera_jpg():
    data = _board_cam().jpeg()
    if data is None:
        raise HTTPException(status_code=503, detail="보드에서 사진이 오지 않습니다 (연결·펌웨어 확인)")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/board/stream")
def board_stream():
    return StreamingResponse(_board_cam().frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/sort/go")
async def sort_go():
    """READY 버튼: 샤오가 인식한 라벨(캔/페트/종이)의 통으로 보낸다. 빈 트레이면 물건을 얹어 달라는 오류."""
    r = robot.sorter.go_now()
    if not r["ok"]:
        raise HTTPException(status_code=r["status"], detail=r["reason"])
    return r


@app.get("/api/tray")
def tray_status():
    """샤오 카메라로 본 트레이 (빈 트레이 기준 사진이 있어야 함)"""
    if robot.tray is None:
        raise HTTPException(status_code=503, detail="샤오 카메라를 쓰지 않습니다 (BOARD_PORT=none 이어야 함)")
    return {"ready": robot.tray.ready, "look": robot.tray.look()}


@app.post("/api/tray/baseline")
def tray_baseline():
    """지금 트레이를 '빈 트레이' 기준 사진으로 저장 (트레이를 비운 뒤에 부를 것)"""
    if robot.tray is None:
        raise HTTPException(status_code=503, detail="샤오 카메라를 쓰지 않습니다 (BOARD_PORT=none 이어야 함)")
    if not robot.tray.set_baseline():
        raise HTTPException(status_code=502, detail="샤오 카메라 사진을 받지 못했습니다")
    return {"ok": True}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
