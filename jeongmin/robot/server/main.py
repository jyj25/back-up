"""라즈봇 웹 조종 서버.

라즈베리파이:  ~/raspbot-venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
노트북(가짜):  ROBOT_MODE=fake uvicorn server.main:app --port 8000
→ 브라우저로 http://<주소>:8000 , API 문서는 /docs

안전장치
- 모든 이동 명령은 duration_ms 뒤에 자동으로 멈춘다 (기본 500ms, 최대 3000ms).
  계속 움직이려면 화면처럼 0.2초마다 같은 명령을 다시 보낸다 → 연결이 끊기면 로봇이 알아서 선다.
- 속도는 MAX_SPEED (기본 150 / 255) 를 넘지 않는다.
- 앞쪽으로 가는 중에 초음파 거리가 OBSTACLE_CM (기본 15cm) 보다 가까우면 멈추고,
  그 상태에서는 앞쪽 이동 명령을 받지 않는다 (뒤·옆·회전은 된다). 0 이면 끔.

다른 웹(팀원 화면)에서 브라우저로 API 를 부르려면 CORS_ORIGINS 에 그 웹 주소를 쉼표로 적는다.
  예) CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5500"   (비워 두면 이 서버의 화면만 허용)
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .camera import Camera
from .drivers import LED_COLORS, MOVES, PAN_RANGE, TILT_RANGE, make_driver

MAX_SPEED = int(os.environ.get("MAX_SPEED", "150"))
OBSTACLE_CM = float(os.environ.get("OBSTACLE_CM", "15"))
FORWARD_MOVES = {"forward", "diag_forward_left", "diag_forward_right"}  # 초음파 센서는 앞에 있다
# 끝의 / 는 브라우저가 보내는 Origin 에 없으므로 떼어 둔다
CORS_ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
STATIC = Path(__file__).parent / "static"


class Robot:
    """드라이버 + 카메라 + 자동 정지 타이머"""

    def __init__(self) -> None:
        self.driver = make_driver()
        self.camera = Camera()
        self._stop_at = 0.0
        self._watchdog: asyncio.Task | None = None
        self.blocked = False  # 장애물 때문에 멈췄는지

    async def start(self) -> None:
        self._watchdog = asyncio.create_task(self._watch())

    async def _watch(self) -> None:
        tick = 0
        while True:
            await asyncio.sleep(0.05)
            tick += 1
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
        if self._watchdog:
            self._watchdog.cancel()
        self.driver.close()
        self.camera.close()


robot: Robot | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global robot
    robot = Robot()
    await robot.start()
    print(f"[robot] mode={robot.driver.mode} camera={robot.camera.kind} max_speed={MAX_SPEED} "
          f"cors={CORS_ORIGINS or '없음'}")
    yield
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
    pan: int | None = Field(default=None, ge=PAN_RANGE[0], le=PAN_RANGE[1], description="좌우 0~180, 90 이 정면")
    tilt: int | None = Field(default=None, ge=TILT_RANGE[0], le=TILT_RANGE[1], description="위아래 0~110")


class BeepIn(BaseModel):
    ms: int = Field(default=150, ge=10, le=2000)


class LedIn(BaseModel):
    color: Literal[tuple(LED_COLORS)] | None = None  # type: ignore[valid-type]  None 이면 끔


@app.get("/api/status")
def status():
    s = robot.driver.state
    return {"mode": s.mode, "moving": s.moving, "speed": s.speed, "pan": s.pan, "tilt": s.tilt,
            "led": s.led, "camera": robot.camera.kind, "max_speed": MAX_SPEED,
            "blocked": robot.blocked, "obstacle_cm": OBSTACLE_CM}


@app.post("/api/move")
def move(body: MoveIn):
    robot.move(body.action, body.speed, body.duration_ms)
    return status()


@app.post("/api/stop")
def stop():
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


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
