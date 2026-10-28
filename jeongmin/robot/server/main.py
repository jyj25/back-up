"""라즈봇 웹 조종 서버.

라즈베리파이:  ~/raspbot-venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
노트북(가짜):  ROBOT_MODE=fake uvicorn server.main:app --port 8000
→ 브라우저로 http://<주소>:8000 , API 문서는 /docs

안전장치
- 모든 이동 명령은 duration_ms 뒤에 자동으로 멈춘다 (기본 500ms, 최대 3000ms).
  계속 움직이려면 화면처럼 0.2초마다 같은 명령을 다시 보낸다 → 연결이 끊기면 로봇이 알아서 선다.
- 속도는 MAX_SPEED (기본 150 / 255) 를 넘지 않는다.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .camera import Camera
from .drivers import LED_COLORS, MOVES, PAN_RANGE, TILT_RANGE, make_driver

MAX_SPEED = int(os.environ.get("MAX_SPEED", "150"))
STATIC = Path(__file__).parent / "static"


class Robot:
    """드라이버 + 카메라 + 자동 정지 타이머"""

    def __init__(self) -> None:
        self.driver = make_driver()
        self.camera = Camera()
        self._stop_at = 0.0
        self._watchdog: asyncio.Task | None = None

    async def start(self) -> None:
        self._watchdog = asyncio.create_task(self._watch())

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            if self.driver.state.moving and time.monotonic() >= self._stop_at:
                await asyncio.to_thread(self.driver.stop)

    def move(self, action: str, speed: int, duration_ms: int) -> None:
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
    print(f"[robot] mode={robot.driver.mode} camera={robot.camera.kind} max_speed={MAX_SPEED}")
    yield
    robot.close()


app = FastAPI(title="Raspbot 조종 서버", lifespan=lifespan)

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
            "led": s.led, "camera": robot.camera.kind, "max_speed": MAX_SPEED}


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
