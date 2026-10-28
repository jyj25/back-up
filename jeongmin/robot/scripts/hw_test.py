"""라즈봇 하드웨어 단계별 점검 (라즈베리파이에서 실행).

    ~/raspbot-venv/bin/python scripts/hw_test.py          # 전부
    ~/raspbot-venv/bin/python scripts/hw_test.py motors   # 하나만: i2c buzzer led ultra line motors move servo camera

⚠️ 모터 단계 전에 **바퀴를 바닥에서 띄운다** (상자 위에 올리기). 단계마다 Enter 를 눌러야 다음으로 간다.
결과는 표로 정리되니 docs/robot-specs.md 의 '측정값' 칸에 옮겨 적는다.
"""
import subprocess
import sys
import time

SPEED = 80  # 점검용 느린 속도 (0~255)
results: dict[str, str] = {}


def ask(msg: str) -> str:
    return input(f"\n{msg} [Enter=계속, s=건너뛰기] ").strip().lower()


def check_i2c(bot=None):
    out = subprocess.run(["/usr/sbin/i2cdetect", "-y", "1"], capture_output=True, text=True).stdout
    found = " 2b" in out
    print(out)
    results["i2c"] = "0x2B 보임" if found else "0x2B 없음 → 배터리 전원 / 기판 연결 확인"
    return found


def buzzer(bot):
    bot.buzzer.on(); time.sleep(0.2); bot.buzzer.off()
    results["buzzer"] = input("  삐 소리가 났나요? (y/n) ")


def led(bot):
    from raspbot.types import LedColor
    for c in (LedColor.RED, LedColor.GREEN, LedColor.BLUE):
        bot.leds.set_all(c); time.sleep(0.6)
    bot.leds.off_all()
    results["led"] = input("  빨강→초록→파랑 순서로 켜졌나요? (y/n) ")


def ultra(bot):
    bot.ultrasonic.enable()
    for _ in range(10):
        print(f"  거리 {bot.ultrasonic.read_cm():6.1f} cm  (손을 앞에 가까이/멀리)"); time.sleep(0.3)
    bot.ultrasonic.disable()
    results["ultrasonic"] = input("  손 거리에 따라 숫자가 바뀌었나요? (y/n) ")


def line(bot):
    for _ in range(10):
        s = bot.line_tracker.read()
        print("  " + "".join("●" if x else "○" for x in (s.x1, s.x2, s.x3, s.x4)) + "  (흰 종이/검은 테이프 위로)"); time.sleep(0.3)
    results["line"] = input("  검은 선 위에서 ●가 바뀌었나요? (y/n) ")


def motors(bot):
    from raspbot.types import MotorDirection, MotorId
    names = {MotorId.L1: "왼쪽 앞", MotorId.L2: "왼쪽 뒤", MotorId.R1: "오른쪽 앞", MotorId.R2: "오른쪽 뒤"}
    wrong = []
    for mid, name in names.items():
        bot.motors.set(mid, MotorDirection.FORWARD, SPEED); time.sleep(0.8); bot.motors.stop()
        ans = input(f"  [{name}] 바퀴가 '앞으로' 돌았나요? (y / n=다른 바퀴가 돎 / r=거꾸로 돎) ")
        if ans != "y":
            wrong.append(f"{name}:{ans}")
    results["motors"] = "모두 정상" if not wrong else "확인 필요 " + ", ".join(wrong)


def move(bot):
    # 메카넘 바퀴 배치(X자)가 맞는지는 '옆으로' 가 제대로 되는지로 확인한다
    for label, fn in [("앞", bot.motors.forward), ("뒤", bot.motors.backward),
                      ("왼쪽 옆", bot.motors.strafe_left), ("오른쪽 옆", bot.motors.strafe_right)]:
        input(f"  '{label}' 으로 1초 움직입니다. 바닥에 내려놓고 Enter (주변 1m 비우기)")
        fn(SPEED); time.sleep(1.0); bot.motors.stop()
    results["move"] = input("  옆 이동이 똑바로 옆으로 갔나요? (y / n=비스듬히 또는 제자리 → 바퀴 롤러 X자 확인) ")


def servo(bot):
    for pan in (90, 30, 150, 90):
        bot.servos.pan.set_angle(pan); time.sleep(0.6)
    for tilt in (90, 30, 110, 90):
        bot.servos.tilt.set_angle(tilt); time.sleep(0.6)
    results["servo"] = input("  카메라가 좌우, 위아래로 움직이고 정면으로 돌아왔나요? (y/n) ")


def camera(bot=None):
    path = "/tmp/raspbot_test.jpg"
    r = subprocess.run(["rpicam-still", "-n", "-t", "800", "-o", path], capture_output=True, text=True)
    results["camera"] = f"사진 저장 {path}" if r.returncode == 0 else "실패: " + (r.stderr.strip().splitlines() or ["?"])[-1]
    print("  " + results["camera"])


STEPS = [("i2c", check_i2c), ("buzzer", buzzer), ("led", led), ("ultra", ultra), ("line", line),
         ("motors", motors), ("move", move), ("servo", servo), ("camera", camera)]


def main():
    only = sys.argv[1:] or [name for name, _ in STEPS]
    if "i2c" in only and not check_i2c() and len(only) > 1:
        print("라즈봇 기판이 안 보여서 멈춥니다."); return
    from raspbot import Robot
    with Robot() as bot:
        try:
            for name, fn in STEPS:
                if name == "i2c" or name not in only:
                    continue
                if name == "motors":
                    print("\n⚠️  바퀴를 바닥에서 띄웠는지 확인하세요!")
                if ask(f"[{name}] 점검") == "s":
                    results[name] = "건너뜀"; continue
                fn(bot)
        finally:
            bot.motors.stop()
    print("\n===== 결과 =====")
    for k, v in results.items():
        print(f"{k:10s} {v}")


if __name__ == "__main__":
    main()
