"""라즈봇 하드웨어를 다루는 드라이버.

- RealDriver: 라즈베리파이 위에서 `raspbot` 라이브러리(I2C 0x2B)로 실제 모터·센서를 움직인다.
- FakeDriver: 노트북에서 하드웨어 없이 시험할 때. 명령을 기록만 하고 그럴듯한 센서값을 돌려준다.

서버(main.py)는 이 두 클래스의 같은 메서드만 쓴다. 새 기능을 넣을 때는 두 클래스에 모두 추가한다.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from .sim import World

# 이동 명령 이름 → raspbot.Motors 메서드 이름
MOVES = {
    "forward": "forward",
    "backward": "backward",
    "turn_left": "turn_left",
    "turn_right": "turn_right",
    "strafe_left": "strafe_left",
    "strafe_right": "strafe_right",
    "diag_forward_left": "diagonal_forward_left",
    "diag_forward_right": "diagonal_forward_right",
    "diag_backward_left": "diagonal_backward_left",
    "diag_backward_right": "diagonal_backward_right",
}
LED_COLORS = ["red", "green", "blue", "yellow", "purple", "cyan", "white"]
PAN_RANGE = (0, 180)
TILT_RANGE = (0, 110)  # 라즈봇 V2 의 위아래 서보는 기구 때문에 110° 까지만
# 라즈봇 키트 리모컨 (실측): 버튼마다 코드를 보내고, 떼면 255 가 남는다.
# 전원 버튼만 코드 0 이라 레지스터가 "없음" 과 같아 보인다 → 아무 코드 없이 255 가 오면 전원 버튼으로 본다.
# 쏟기 서보: 고장 난 위아래 서보 자리(S2, 라이브러리의 tilt 채널, 0~110°)에 키트 서보를 꽂아 트레이를 기울인다
DUMP_REST = int(os.environ.get("DUMP_REST", "0"))     # 평소 (트레이 수평)
DUMP_ANGLE = int(os.environ.get("DUMP_ANGLE", "90"))  # 쏟을 때
DUMP_HOLD_S = 1.5
IR_POWER = 0
IR_RELEASE = 255


@dataclass
class RobotState:
    mode: str
    moving: str | None = None
    speed: int = 0
    pan: int = 90
    tilt: int = 90
    led: str | None = None
    history: list[str] = field(default_factory=list)  # FakeDriver 용 명령 기록


class FakeDriver:
    """하드웨어 없이 동작을 흉내 낸다. 테스트와 화면 개발용."""

    mode = "fake"

    def __init__(self) -> None:
        self.state = RobotState(mode=self.mode)
        self.world = World()  # 가짜 위치·마커·거리 (sim.py)
        self.ir_queue: list[int] = []  # 테스트에서 리모컨 누름을 넣는 곳

    def _log(self, text: str) -> None:
        self.state.history.append(text)
        del self.state.history[:-100]

    def move(self, action: str, speed: int) -> None:
        self.state.moving, self.state.speed = action, speed
        self.world.set_motion(action, speed)
        self._log(f"move {action} {speed}")

    def stop(self) -> None:
        self.state.moving, self.state.speed = None, 0
        self.world.set_motion(None, 0)
        self._log("stop")

    def set_servo(self, pan: int | None, tilt: int | None) -> None:
        if pan is not None:
            self.state.pan = pan
        if tilt is not None:
            self.state.tilt = tilt
        self._log(f"servo {self.state.pan} {self.state.tilt}")

    def distance_cm(self) -> float:
        return self.world.distance_cm()

    def line(self) -> list[bool]:
        return [False, True, True, False]

    def beep(self, ms: int) -> None:
        self._log(f"beep {ms}")

    def set_led(self, color: str | None) -> None:
        self.state.led = color
        self._log(f"led {color}")

    def dump(self) -> None:
        """실은 물건 쏟기"""
        self._log("dump")

    def remote_key(self) -> int | None:
        """리모컨 버튼이 새로 눌렸으면 그 코드, 아니면 None"""
        return self.ir_queue.pop(0) if self.ir_queue else None

    def close(self) -> None:
        self.stop()


class RealDriver(FakeDriver):
    """라즈베리파이에서 raspbot 라이브러리로 실제 하드웨어를 움직인다."""

    mode = "real"

    def __init__(self) -> None:
        from raspbot import Robot  # 라즈베리파이에만 설치돼 있다
        from raspbot.types import LedColor

        super().__init__()
        self._LedColor = LedColor
        self._bot = Robot()
        self._lock = threading.Lock()  # I2C 는 한 번에 한 명령씩
        self._bot.motors.stop()
        self._bot.servos.pan.set_angle(90)
        self._bot.servos.tilt.set_angle(DUMP_REST)  # S2 = 쏟기 서보 → 켜질 때 트레이 수평
        self._bot.ultrasonic.enable()
        self._bot.ir.enable()
        self._ir_prev = self._bot.ir.read_keycode()  # 켜기 전에 남아 있던 값은 누름으로 치지 않는다

    def move(self, action: str, speed: int) -> None:
        with self._lock:
            getattr(self._bot.motors, MOVES[action])(speed)
        super().move(action, speed)

    def stop(self) -> None:
        with self._lock:
            self._bot.motors.stop()
        super().stop()

    def set_servo(self, pan: int | None, tilt: int | None) -> None:
        with self._lock:
            if pan is not None:
                self._bot.servos.pan.set_angle(pan)
            if tilt is not None:
                self._bot.servos.tilt.set_angle(tilt)
        super().set_servo(pan, tilt)

    def distance_cm(self) -> float:
        with self._lock:
            return round(self._bot.ultrasonic.read_cm(), 1)

    def line(self) -> list[bool]:
        with self._lock:
            s = self._bot.line_tracker.read()
        return [bool(s.x1), bool(s.x2), bool(s.x3), bool(s.x4)]

    def remote_key(self) -> int | None:
        with self._lock:
            code = self._bot.ir.read_keycode()
        prev, self._ir_prev = self._ir_prev, code
        if code == prev or code is None:
            return None
        if code == IR_RELEASE:
            return IR_POWER if prev is None else None  # 버튼 코드 없이 바로 255 → 전원 버튼
        return code

    def beep(self, ms: int) -> None:
        # raspbot 의 beep() 는 update() 를 계속 불러야 꺼지므로 직접 켜고 끈다
        with self._lock:
            self._bot.buzzer.on()
        time.sleep(ms / 1000)
        with self._lock:
            self._bot.buzzer.off()
        super().beep(ms)

    def set_led(self, color: str | None) -> None:
        with self._lock:
            if color is None:
                self._bot.leds.off_all()
            else:
                self._bot.leds.set_all(getattr(self._LedColor, color.upper()))
        super().set_led(color)

    def dump(self) -> None:
        # 노란 LED + 삐 → 쏟기 서보로 트레이를 기울였다가 원위치
        self.set_led("yellow")
        self.beep(120)
        with self._lock:
            self._bot.servos.tilt.set_angle(DUMP_ANGLE)
        time.sleep(DUMP_HOLD_S)
        with self._lock:
            self._bot.servos.tilt.set_angle(DUMP_REST)
        time.sleep(0.5)
        self.set_led(None)
        super().dump()

    def close(self) -> None:
        try:
            self.stop()
            with self._lock:
                self._bot.ultrasonic.disable()
                self._bot.ir.disable()
                self._bot.leds.off_all()
        finally:
            self._bot.close()


def make_driver() -> FakeDriver:
    """ROBOT_MODE=real|fake. 지정하지 않으면 I2C 와 raspbot 이 있으면 real, 아니면 fake."""
    mode = os.environ.get("ROBOT_MODE", "").lower()
    if mode == "fake":
        return FakeDriver()
    if mode == "real":
        return RealDriver()
    try:
        if os.path.exists("/dev/i2c-1"):
            return RealDriver()
    except Exception as e:  # 라즈봇 기판이 안 붙어 있으면 여기로 온다
        print(f"[robot] 실제 하드웨어를 못 열어서 fake 모드로 시작: {e}")
    return FakeDriver()
