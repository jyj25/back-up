import os
import time

os.environ["ROBOT_MODE"] = "fake"   # 하드웨어 없이
os.environ["CAMERA"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from server import main  # noqa: E402


def client():
    return TestClient(main.app)


def test_status_fake_mode():
    with client() as c:
        s = c.get("/api/status").json()
        assert s["mode"] == "fake" and s["moving"] is None and s["camera"] == "none"


def test_move_then_auto_stop():
    with client() as c:
        s = c.post("/api/move", json={"action": "forward", "speed": 100, "duration_ms": 100}).json()
        assert s["moving"] == "forward" and s["speed"] == 100
        time.sleep(0.4)  # duration 이 지나면 서버가 알아서 멈춘다 (연결이 끊겨도 안전)
        assert c.get("/api/status").json()["moving"] is None


def test_speed_is_capped():
    with client() as c:
        s = c.post("/api/move", json={"action": "strafe_left", "speed": 255}).json()
        assert s["speed"] == main.MAX_SPEED
        c.post("/api/stop")


def test_validation():
    with client() as c:
        assert c.post("/api/move", json={"action": "fly"}).status_code == 422
        assert c.post("/api/move", json={"action": "forward", "duration_ms": 10000}).status_code == 422
        assert c.post("/api/servo", json={"tilt": 150}).status_code == 422   # 위아래는 110° 까지
        assert c.post("/api/led", json={"color": "pink"}).status_code == 422


def test_servo_led_beep_sensors():
    with client() as c:
        s = c.post("/api/servo", json={"pan": 45, "tilt": 100}).json()
        assert (s["pan"], s["tilt"]) == (45, 100)
        assert c.post("/api/led", json={"color": "green"}).json()["led"] == "green"
        assert c.post("/api/led", json={"color": None}).json()["led"] is None
        assert c.post("/api/beep", json={"ms": 50}).json() == {"ok": True}
        assert 0 < c.get("/api/distance").json()["cm"] < 400
        assert len(c.get("/api/line").json()["sensors"]) == 4


def test_camera_missing_is_503_and_ui_served():
    with client() as c:
        assert c.get("/api/camera.jpg").status_code == 503
        r = c.get("/")
        assert r.status_code == 200 and "라즈봇 조종" in r.text


def test_obstacle_blocks_forward_but_not_backward():
    with client() as c:
        main.robot.driver.distance_cm = lambda: 8.0   # 앞 8cm 에 벽
        s = c.post("/api/move", json={"action": "forward", "speed": 100}).json()
        assert s["moving"] is None and s["blocked"] is True
        s = c.post("/api/move", json={"action": "backward", "speed": 100}).json()
        assert s["moving"] == "backward" and s["blocked"] is False
        c.post("/api/stop")


def test_obstacle_stops_while_moving():
    with client() as c:
        d = main.robot.driver
        d.distance_cm = lambda: 50.0
        assert c.post("/api/move", json={"action": "forward", "duration_ms": 2000}).json()["moving"] == "forward"
        d.distance_cm = lambda: 10.0  # 가는 중에 물체가 다가옴
        time.sleep(0.4)
        s = c.get("/api/status").json()
        assert s["moving"] is None and s["blocked"] is True


def test_remote_power_button_stops():
    with client() as c:
        assert c.post("/api/move", json={"action": "forward", "speed": 100, "duration_ms": 3000}).json()["moving"]
        main.robot.driver.ir_queue.append(5)       # 다른 버튼은 무시
        time.sleep(0.2)
        assert c.get("/api/status").json()["moving"] == "forward"
        main.robot.driver.ir_queue.append(main.IR_STOP_KEY)  # 전원 버튼
        time.sleep(0.2)
        assert c.get("/api/status").json()["moving"] is None


def test_real_driver_remote_decoding():
    # 실측 순서: 일반 버튼은 코드 → 255, 전원 버튼은 (0 = 없음) → 255
    import threading
    from types import SimpleNamespace

    from server.drivers import IR_POWER, RealDriver

    reads = iter([5, 5, 255, 255, None, 255, 255, 18, 255])
    d = object.__new__(RealDriver)
    d._lock = threading.Lock()
    d._bot = SimpleNamespace(ir=SimpleNamespace(read_keycode=lambda: next(reads)))
    d._ir_prev = 255
    got = [d.remote_key() for _ in range(9)]
    assert [k for k in got if k is not None] == [5, IR_POWER, 18]


def test_board_camera_off_in_fake_mode_and_cams_page():
    with client() as c:
        assert c.get("/api/board/camera.jpg").status_code == 503
        r = c.get("/cams.html")
        assert r.status_code == 200 and "/api/board/stream" in r.text
