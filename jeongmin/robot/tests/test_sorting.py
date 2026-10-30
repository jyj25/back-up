import asyncio
import os
import threading
import time

os.environ["ROBOT_MODE"] = "fake"
os.environ["CAMERA"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from server import main  # noqa: E402
from server.sorter import Sorter, parse_line  # noqa: E402
from tests.test_navigation import VirtualClock  # noqa: E402


def test_parse_line_keeps_only_json_objects():
    assert parse_line('{"class":"can","conf":0.93,"ms":173}\r\n') == {"class": "can", "conf": 0.93, "ms": 173}
    assert parse_line(b'{"error":"camera"}\n') == {"error": "camera"}
    assert parse_line("ESP-ROM:esp32s3-20210327") is None      # 부팅 로그
    assert parse_line('{"class":"can",') is None               # 끊긴 줄
    assert parse_line("[1, 2]") is None and parse_line("") is None


def test_verdict_rules_and_manual_override_is_recorded():
    with TestClient(main.app) as c:
        v = lambda obj: c.post("/api/verdict", json=obj).json()  # noqa: E731
        assert v({"class": "can", "conf": 0.95})["reason"] == "자동 출발 꺼짐"   # 기본은 꺼짐
        assert c.post("/api/sort", json={"auto": True}).json()["auto"] is True
        assert v({"class": None, "conf": 0.4})["reason"] == "판정 없음"
        assert v({"class": "empty", "conf": 0.99})["reason"] == "빈 트레이"
        assert v({"class": "glass", "conf": 0.99})["reason"].startswith("모르는 종류")
        assert v({"class": "home", "conf": 0.99})["reason"].startswith("모르는 종류")
        assert v({"class": "can", "conf": 0.5})["reason"].startswith("확신도 낮음")
        assert v({"error": "camera"})["reason"] == "보드 오류: camera"
        assert v({"event": "stuck", "class": "can", "conf": 0.9})["reason"] == "판정 아님 (stuck)"
        assert c.get("/api/sort").json()["last_verdict"]["result"] == "판정 아님 (stuck)"

        r = v({"class": "pet", "conf": 0.91, "event": "decision"})
        assert r["accepted"] is True
        m = c.get("/api/mission").json()
        assert m["running"] and (m["label"], m["by"], m["confidence"]) == ("pet", "ai", 0.91)
        assert c.get("/api/status").json()["auto_sort"] is True
        assert v({"class": "can", "conf": 0.99})["reason"] == "임무 중"          # 하던 임무가 우선

        c.post("/api/stop")                                                   # 수동 정지 → 취소
        time.sleep(0.1)
        h = c.get("/api/history").json()
        assert h["items"][-1]["result"] == "cancelled" and h["items"][-1]["by"] == "ai"
        assert h["items"][-1]["label"] == "pet" and h["items"][-1]["confidence"] == 0.91
        assert h["bins"] == {"can": 0, "pet": 0, "paper": 0}                   # 완료가 아니면 세지 않음

        assert c.post("/api/mission", json={"station": "paper"}).status_code == 202   # 웹에서 보낸 임무
        assert c.get("/api/mission").json()["by"] == "web"
        c.post("/api/mission/cancel")
        time.sleep(0.1)
        last = c.get("/api/history").json()["items"][-1]
        assert (last["label"], last["by"], last["confidence"]) == ("paper", "web", None)
        assert c.post("/api/history/reset", json={"station": "metal"}).status_code == 422


def test_done_mission_counts_and_history_survives_restart(tmp_path):
    file = tmp_path / "history.jsonl"
    robot = main.Robot()
    clock = VirtualClock()
    robot.driver.world.set_clock(clock)
    robot.mission.sleep = clock.sleep
    robot.sorter = Sorter(robot, main.STATIONS, auto=True, history_file=file)

    async def run():
        assert robot.sorter.handle({"class": "pet", "conf": 0.9, "ms": 170})["accepted"]
        await asyncio.wait_for(robot.mission.wait(), 20)
        await asyncio.sleep(0)  # 기록 작업이 마무리될 시간

    try:
        asyncio.run(run())
    finally:
        robot.close()
    h = robot.sorter.history()
    assert h["bins"]["pet"] == 1 and h["items"][0]["result"] == "done" and h["items"][0]["seconds"] >= 0

    again = Sorter(robot, main.STATIONS, history_file=file)   # 서버를 다시 켠 것처럼
    assert again.history() == h
    again.reset("pet")
    assert Sorter(robot, main.STATIONS, history_file=file).history()["bins"]["pet"] == 0
    assert len(Sorter(robot, main.STATIONS, history_file=file).history()["items"]) == 1  # 기록은 남는다


def test_board_line_from_reader_thread_starts_mission():
    robot = main.Robot()
    robot.sorter.auto = True

    async def run():
        await robot.start()
        lines = ["ESP-ROM boot log", '{"class":null,"conf":0.3}', '{"class":"can","conf":0.88,"ms":160}']
        t = threading.Thread(target=lambda: [robot._on_board_line(x) for x in lines])  # 보드 읽기 스레드 흉내
        t.start()
        t.join()
        for _ in range(50):
            if robot.mission.running:
                break
            await asyncio.sleep(0.01)
        running, label = robot.mission.running, (robot.sorter.current or {}).get("label")
        await robot.mission.abort("시험 끝")
        return running, label

    try:
        running, label = asyncio.run(run())
    finally:
        robot.close()
    assert running and label == "can"
    assert robot.sorter.last_verdict["source"] == "board"


def test_board_reader_reads_lines_and_reconnects(monkeypatch):
    """pyserial 대신 가짜 모듈: 첫 연결은 끊기고(뽑힘), 다시 연결해서 줄을 읽는다"""
    import sys
    import types

    from server.board import BoardReader

    opened, got = [], []

    class FakeSerial:
        def __init__(self, path, baud, timeout):
            opened.append(path)
            self.lines = [b'{"class":"can","conf":0.9}\n'] if len(opened) > 1 else []

        def __enter__(self):
            if len(opened) == 1:
                raise fake.SerialException("device disconnected")
            return self

        def __exit__(self, *a):
            return False

        def readline(self):
            time.sleep(0.01)
            return self.lines.pop(0) if self.lines else b""

    fake = types.SimpleNamespace(Serial=FakeSerial, SerialException=type("SerialException", (OSError,), {}))
    monkeypatch.setitem(sys.modules, "serial", fake)
    monkeypatch.setattr("server.board.threading.Event.wait", lambda self, t=None: time.sleep(0.01))

    r = BoardReader("/dev/ttyACM9", got.append)
    r.start()
    for _ in range(200):
        if got:
            break
        time.sleep(0.01)
    r.stop()
    assert got == ['{"class":"can","conf":0.9}\n'] and opened[:2] == ["/dev/ttyACM9", "/dev/ttyACM9"]
    assert r.status()["last_line_at"] is not None
    assert BoardReader("none", got.append).enabled is False
